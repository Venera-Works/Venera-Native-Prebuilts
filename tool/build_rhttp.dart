import 'dart:io';
import 'dart:typed_data';

import 'package:args/args.dart';
import 'package:build_tool/src/artifacts_provider.dart';
import 'package:build_tool/src/builder.dart';
import 'package:build_tool/src/cargo.dart';
import 'package:build_tool/src/crate_hash.dart';
import 'package:build_tool/src/logging.dart';
import 'package:build_tool/src/options.dart';
import 'package:build_tool/src/precompile_binaries.dart';
import 'package:build_tool/src/rustup.dart';
import 'package:build_tool/src/target.dart';
import 'package:ed25519_edwards/ed25519_edwards.dart';
import 'package:hex/hex.dart';
import 'package:logging/logging.dart';
import 'package:path/path.dart' as path;

final _log = Logger('venera_precompile');

void main(List<String> arguments) async {
  initLogging();

  final parser = ArgParser()
    ..addOption(
      'manifest-dir',
      mandatory: true,
      help: 'Directory containing Cargo.toml (e.g. build/package/rust)',
    )
    ..addOption(
      'output-dir',
      mandatory: true,
      help: 'Directory to store compiled and signed artifacts',
    )
    ..addMultiOption(
      'target',
      help: 'Rust target triple to build. Can be specified multiple times.',
    )
    ..addOption(
      'android-sdk-location',
      help: 'Location of Android SDK (required for Android targets)',
    )
    ..addOption(
      'android-ndk-version',
      help: 'Android NDK version (e.g. 28.0.13004108)',
    )
    ..addOption(
      'android-min-sdk-version',
      help: 'Android minimum SDK version (e.g. 21)',
    )
    ..addOption(
      'temp-dir',
      help: 'Directory to store temporary build artifacts',
    )
    ..addFlag(
      'verbose',
      abbr: 'v',
      defaultsTo: false,
      help: 'Enable verbose logging',
    );

  final ArgResults argResults;
  try {
    argResults = parser.parse(arguments);
  } on FormatException catch (e) {
    stderr.writeln(e.message);
    stderr.writeln(parser.usage);
    exit(1);
  }

  final verbose = argResults['verbose'] as bool;
  if (verbose) {
    enableVerboseLogging();
  }

  final manifestDir = argResults['manifest-dir'] as String;
  if (!Directory(manifestDir).existsSync()) {
    stderr.writeln('Manifest directory does not exist: $manifestDir');
    exit(1);
  }

  final outputDir = argResults['output-dir'] as String;
  Directory(outputDir).createSync(recursive: true);

  // Read PRIVATE_KEY from environment
  final privateKeyString = Platform.environment['PRIVATE_KEY'];
  if (privateKeyString == null || privateKeyString.trim().isEmpty) {
    stderr.writeln('Error: Environment variable PRIVATE_KEY is not set.');
    exit(1);
  }

  final List<int> privateKeyBytes;
  try {
    privateKeyBytes = HEX.decode(privateKeyString.trim());
  } catch (e) {
    stderr.writeln('Error: Failed to decode PRIVATE_KEY from hex.');
    exit(1);
  }

  if (privateKeyBytes.length != 64) {
    stderr.writeln('Error: PRIVATE_KEY must be a 64-byte Ed25519 private key.');
    exit(1);
  }
  final privateKey = PrivateKey(Uint8List.fromList(privateKeyBytes));

  // Verify that the private key matches the public key configured in cargokit.yaml
  final crateOptions = CargokitCrateOptions.load(manifestDir: manifestDir);
  final precompiledConfig = crateOptions.precompiledBinaries;
  if (precompiledConfig == null) {
    stderr.writeln(
      'Error: cargokit.yaml in $manifestDir has no precompiled_binaries configuration.',
    );
    exit(1);
  }

  final derivedPublicKey = public(privateKey);
  final derivedHex = HEX.encode(derivedPublicKey.bytes).toLowerCase();
  final configuredHex = HEX
      .encode(precompiledConfig.publicKey.bytes)
      .toLowerCase();

  if (derivedHex != configuredHex) {
    stderr.writeln(
      'Error: Private key does not match public key configured in cargokit.yaml!\n'
      'Configured public key: $configuredHex\n'
      'Derived public key:    $derivedHex',
    );
    exit(1);
  }
  _log.info('Key verification passed (public key: $configuredHex)');

  // Determine targets to build
  final targetStrings = argResults['target'] as List<String>;
  final List<Target> targets;
  if (targetStrings.isEmpty) {
    targets = [
      ...Target.buildableTargets(),
      if (argResults['android-sdk-location'] != null)
        ...Target.androidTargets(),
    ];
  } else {
    targets = [];
    for (final t in targetStrings) {
      final target = Target.forRustTriple(t);
      if (target == null) {
        stderr.writeln('Error: Unknown target triple: $t');
        exit(1);
      }
      targets.add(target);
    }
  }

  _log.info('Targets to build: ${targets.map((t) => t.rust).toList()}');

  // Parse Android options
  final androidSdkLocation = argResults['android-sdk-location'] as String?;
  final androidNdkVersion = argResults['android-ndk-version'] as String?;
  final androidMinSdkVersionString =
      argResults['android-min-sdk-version'] as String?;
  int? androidMinSdkVersion;
  if (androidMinSdkVersionString != null) {
    androidMinSdkVersion = int.tryParse(androidMinSdkVersionString);
    if (androidMinSdkVersion == null) {
      stderr.writeln(
        'Error: Invalid android-min-sdk-version: $androidMinSdkVersionString',
      );
      exit(1);
    }
  }

  final crateInfo = CrateInfo.load(manifestDir);
  final crateHash = CrateHash.compute(manifestDir);
  _log.info('Crate: ${crateInfo.packageName}, hash: $crateHash');

  final tempDirOption = argResults['temp-dir'] as String?;
  final Directory tempDir;
  final bool isCustomTempDir = tempDirOption != null;
  if (isCustomTempDir) {
    tempDir = Directory(tempDirOption);
  } else {
    tempDir = Directory.systemTemp.createTempSync('venera_precompile_');
  }
  tempDir.createSync(recursive: true);

  final isAndroid = androidSdkLocation != null;
  final buildEnvironment = BuildEnvironment(
    configuration: BuildConfiguration.release,
    crateOptions: crateOptions,
    targetTempDir: tempDir.path,
    manifestDir: manifestDir,
    crateInfo: crateInfo,
    isAndroid: isAndroid,
    androidSdkPath: androidSdkLocation,
    androidNdkVersion: androidNdkVersion,
    androidMinSdkVersion: androidMinSdkVersion,
  );

  final rustup = Rustup();

  try {
    for (final target in targets) {
      _log.info('Building for target: ${target.rust}');

      final builder = RustBuilder(
        target: target,
        environment: buildEnvironment,
      );
      builder.prepare(rustup);
      final buildArtifactsDir = await builder.build();

      final artifactNames = getArtifactNames(
        target: target,
        libraryName: crateInfo.packageName,
        remote: true,
      );

      _log.info('Artifact names for ${target.rust}: $artifactNames');

      for (final name in artifactNames) {
        final sourceFile = File(path.join(buildArtifactsDir, name));
        if (!sourceFile.existsSync()) {
          throw Exception(
            'Build artifact missing: ${sourceFile.path} for target ${target.rust}',
          );
        }

        final data = sourceFile.readAsBytesSync();
        if (data.isEmpty) {
          throw Exception(
            'Build artifact is empty: ${sourceFile.path} for target ${target.rust}',
          );
        }

        final artifactFileName = PrecompileBinaries.fileName(target, name);
        final signatureFileName = PrecompileBinaries.signatureFileName(
          target,
          name,
        );

        final targetArtifactFile = File(path.join(outputDir, artifactFileName));
        final targetSigFile = File(path.join(outputDir, signatureFileName));

        // Write binary artifact
        targetArtifactFile.writeAsBytesSync(data);
        _log.info('Saved artifact: ${targetArtifactFile.path}');

        // Sign artifact and verify signature
        final signature = sign(privateKey, data);
        final verified = verify(derivedPublicKey, data, signature);
        if (!verified) {
          throw Exception(
            'Self-verification of signature failed for $artifactFileName',
          );
        }
        targetSigFile.writeAsBytesSync(signature);
        _log.info('Saved signature: ${targetSigFile.path}');
      }
    }

    // Copy license files to output directory
    final packageRoot = Directory(manifestDir).parent.path;
    final rhttpLicense = File(path.join(packageRoot, 'LICENSE'));
    if (rhttpLicense.existsSync()) {
      final destLicense = File(path.join(outputDir, 'LICENSE'));
      rhttpLicense.copySync(destLicense.path);
      _log.info('Copied rhttp license -> ${destLicense.path}');
    } else {
      _log.warning('rhttp LICENSE not found at ${rhttpLicense.path}');
    }

    final cargokitLicense = File(path.join(packageRoot, 'cargokit', 'LICENSE'));
    if (cargokitLicense.existsSync()) {
      final destCargokitLicense = File(
        path.join(outputDir, 'LICENSE-cargokit'),
      );
      cargokitLicense.copySync(destCargokitLicense.path);
      _log.info('Copied Cargokit license -> ${destCargokitLicense.path}');
    } else {
      _log.warning('Cargokit LICENSE not found at ${cargokitLicense.path}');
    }

    _log.info(
      'All requested targets compiled, signed, and saved to $outputDir',
    );
  } finally {
    if (!isCustomTempDir && tempDir.existsSync()) {
      try {
        tempDir.deleteSync(recursive: true);
      } catch (e) {
        _log.warning(
          'Failed to clean up temporary directory ${tempDir.path}: $e',
        );
      }
    }
  }
}
