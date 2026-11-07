package dev.bogdan.jobs_manager

import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.MessageDigest

// Installs app updates downloaded from the job service, through Android's package installer,
// saves files such as the CV to Downloads, and draws PDF pages for the app's viewer.
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "fieldwork/update").apply {
            setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "info" -> result.success(info())
                        "openInstallSettings" -> {
                            startActivity(
                                if (Build.VERSION.SDK_INT >= 26) Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))
                                else Intent(Settings.ACTION_SECURITY_SETTINGS),
                            )
                            result.success(null)
                        }
                        "install" -> {
                            val path = call.argument<String>("path")!!
                            val sha256 = call.argument<String>("sha256")!!
                            // Hashing and copying 18 MB would stall the UI thread.
                            Thread {
                                try {
                                    install(path, sha256)
                                    runOnUiThread { result.success(null) }
                                } catch (e: Exception) {
                                    runOnUiThread { result.error("update", e.message ?: e.javaClass.simpleName, null) }
                                }
                            }.start()
                        }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    result.error("update", e.message ?: e.javaClass.simpleName, null)
                }
            }
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "fieldwork/files").setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "save" -> {
                        val name = call.argument<String>("name")!!
                        val mime = call.argument<String>("mime")!!
                        val bytes = call.argument<ByteArray>("bytes")!!
                        Thread {
                            try {
                                val saved = Downloads.save(this, name, mime, bytes)
                                runOnUiThread { result.success(saved) }
                            } catch (e: Exception) {
                                runOnUiThread { result.error("files", e.message ?: e.javaClass.simpleName, null) }
                            }
                        }.start()
                    }
                    "open" -> {
                        Downloads.open(this, call.argument<String>("uri")!!, call.argument<String>("mime")!!)
                        result.success(null)
                    }
                    "render" -> {
                        val bytes = call.argument<ByteArray>("bytes")!!
                        val width = call.argument<Int>("width")!!
                        // Drawing and compressing a page takes a moment; keep it off the UI thread.
                        Thread {
                            try {
                                val pages = PdfPages.render(this, bytes, width)
                                runOnUiThread { result.success(pages) }
                            } catch (e: Exception) {
                                runOnUiThread { result.error("files", e.message ?: e.javaClass.simpleName, null) }
                            }
                        }.start()
                    }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) {
                result.error("files", e.message ?: e.javaClass.simpleName, null)
            }
        }
    }

    private fun info(): Map<String, Any> {
        val pkg = packageManager.getPackageInfo(packageName, 0)
        val code = if (Build.VERSION.SDK_INT >= 28) pkg.longVersionCode else @Suppress("DEPRECATION") pkg.versionCode.toLong()
        return mapOf(
            "versionCode" to code,
            "versionName" to (pkg.versionName ?: ""),
            "canInstall" to (Build.VERSION.SDK_INT < 26 || packageManager.canRequestPackageInstalls()),
            "cacheDir" to cacheDir.absolutePath,
        )
    }

    private fun install(path: String, sha256: String) {
        val apk = File(path)
        val digest = MessageDigest.getInstance("SHA-256")
        apk.inputStream().use { input ->
            val buffer = ByteArray(1 shl 16)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        if (digest.digest().joinToString("") { "%02x".format(it) } != sha256.lowercase()) {
            apk.delete()
            throw IllegalStateException("The download does not match the service's build. Try again.")
        }
        val installer = packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(packageName)
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            apk.inputStream().use { input ->
                session.openWrite("fieldwork.apk", 0, apk.length()).use { output ->
                    input.copyTo(output)
                    session.fsync(output)
                }
            }
            // Status goes to a non-exported receiver: the launcher activity is exported, so any app could fake it.
            val status = Intent(this, InstallStatusReceiver::class.java)
            val pending = PendingIntent.getBroadcast(this, id, status, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
            InstallStatusReceiver.sessions.add(id)
            session.commit(pending.intentSender)
        }
        apk.delete()
    }

    override fun onDestroy() {
        channel = null
        super.onDestroy()
    }

    companion object {
        var channel: MethodChannel? = null
    }
}
