import 'dart:convert';
import 'dart:io';
import 'package:nemc_support_dart/mpay.dart';

Map<String, dynamic> readJson(String path) =>
    Map<String, dynamic>.from(jsonDecode(File(path).readAsStringSync()));

// The Python wrapper creates this private directory before starting Dart.
void savePrivate(String path, Map<String, dynamic> data) {
  final temporary = File('$path.$pid.tmp');
  temporary.writeAsStringSync(jsonEncode(data), flush: true);
  final chmod = Process.runSync('/bin/chmod', ['600', temporary.path]);
  if (chmod.exitCode != 0) throw StateError('Cannot protect output file');
  temporary.renameSync(path);
}

Future<void> main(List<String> args) async {
  if (args.length != 4) {
    stderr.writeln(
      'Usage: login.dart CONFIG INPUT DEVICE_CACHE SESSION_OUTPUT',
    );
    exitCode = 2;
    return;
  }
  var phase = 'prepare';
  final secrets = <String>[];
  try {
    final config = readJson(args[0]);
    final input = readJson(args[1]);
    secrets.addAll([input['username'] as String, input['password'] as String]);
    final appData = Map<String, dynamic>.from(config['mpay_app']);
    final generated = MPayAppInfo.generate().toJson();
    final app = MPayAppInfo.fromJson({...generated, ...appData});
    final agent = config['user_agent'] as String;
    MPayDeviceInfo device;
    MPayRemoteDevice remote;
    final cached = File(args[2]);
    if (cached.existsSync()) {
      final data = readJson(args[2]);
      if (data['game_id'] != app.gameId) {
        throw StateError('Device cache belongs to another product');
      }
      device = MPayDeviceInfo.fromJson(data['local_device']);
      remote = MPayRemoteDevice.fromJson(data['remote_device']);
    } else {
      device = MPayDeviceInfo.generate();
      stdout.writeln('Registering a device for the developer APK product.');
      phase = 'register_device';
      remote = await MPayClient.requestRemoteDevice(
        app,
        device,
        userAgent: agent,
      );
      savePrivate(args[2], {
        'game_id': app.gameId,
        'local_device': device.toJson(),
        'remote_device': remote.toJson(),
      });
    }
    final client = MPayClient(
      remote.id,
      remote.key,
      appInfo: app,
      deviceInfo: device,
      userAgent: agent,
    );
    stdout.writeln(
      'Authenticating with MPay; credentials will not be printed.',
    );
    secrets.addAll([remote.id, remote.key]);
    phase = 'login';
    await client.login(
      input['username'] as String,
      input['password'] as String,
    );
    final sauth = client.getSAuthJson().toJson();
    sauth['source_platform'] = '';
    sauth['source_app_channel'] = '';
    savePrivate(args[3], {
      'schema_version': 1,
      'package_name': config['package_name'],
      'created_at': DateTime.now().millisecondsSinceEpoch ~/ 1000,
      'sauth': sauth,
      'profile': client.userInfo == null
          ? <String, dynamic>{}
          : {
              for (final key in [
                'nickname',
                'realname_status',
                'ext_access_token',
              ])
                if (client.userInfo!.containsKey(key))
                  key: client.userInfo![key],
            },
    });
    stdout.writeln(
      'MPay login succeeded. Private SAuth file is ready for the launcher.',
    );
    // Consume the password input after successful login, never retain it in SAuth.
    File(args[1]).deleteSync();
  } on MPayException catch (error) {
    // Raw server responses/reasons can contain identity data and challenge URLs.
    var reason = error.message;
    for (final secret in secrets) {
      if (secret.isNotEmpty) reason = reason.replaceAll(secret, '[redacted]');
    }
    reason = reason
        .replaceAll(RegExp(r'https?://\S+'), '[URL omitted]')
        .replaceAll(RegExp(r'[A-Za-z0-9_+=/.-]{24,}'), '[identifier omitted]');
    stderr.writeln(
      'MPay rejected $phase (code ${error.code}): ${reason.substring(0, reason.length > 200 ? 200 : reason.length)}',
    );
    exitCode = 3;
  } catch (error) {
    stderr.writeln(
      'Login helper failed (${error.runtimeType}); no credentials printed.',
    );
    exitCode = 4;
  }
}
