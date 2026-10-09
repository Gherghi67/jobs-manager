package dev.bogdan.jobs_manager

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import java.util.Collections

// Receives the package installer's result for sessions MainActivity started. Not exported.
class InstallStatusReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        if (id !in sessions) return
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_INTENT)
                }
                // Only ever open the system's install confirmation, and pass on no file grants.
                if (confirm == null || confirm.action != CONFIRM_INSTALL) {
                    sessions.remove(id)
                    failed("The update was not installed.")
                    return
                }
                confirm.flags = (confirm.flags and GRANTS.inv()) or Intent.FLAG_ACTIVITY_NEW_TASK
                context.startActivity(confirm)
            }
            PackageInstaller.STATUS_SUCCESS -> sessions.remove(id)
            else -> {
                sessions.remove(id)
                failed(intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "The update was not installed.")
            }
        }
    }

    private fun failed(message: String) {
        MainActivity.channel?.invokeMethod("installFailed", message)
    }

    companion object {
        val sessions: MutableSet<Int> = Collections.synchronizedSet(mutableSetOf())
        private const val CONFIRM_INSTALL = "android.content.pm.action.CONFIRM_INSTALL"
        private const val GRANTS = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or Intent.FLAG_GRANT_PREFIX_URI_PERMISSION
    }
}
