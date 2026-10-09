package dev.bogdan.jobs_manager

import android.annotation.TargetApi
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.File

// Saves files from the job service, such as the CV, to the phone's public Downloads folder.
object Downloads {
    private const val FOLDER = "Download/"

    fun save(context: Context, name: String, mime: String, bytes: ByteArray): Map<String, String> {
        if (Build.VERSION.SDK_INT < 29) throw IllegalStateException("Saving to Downloads needs Android 10 or newer.")
        return saveToMediaStore(context, File(name).name.ifBlank { "download" }, mime, bytes)
    }

    // Overwrites the copy Fieldwork saved before, so Downloads keeps one CV instead of "CV (1).pdf".
    @TargetApi(29)
    private fun saveToMediaStore(context: Context, name: String, mime: String, bytes: ByteArray): Map<String, String> {
        val resolver = context.contentResolver
        val collection = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        // Without storage permission the query only returns files Fieldwork created.
        val existing = resolver.query(
            collection,
            arrayOf(MediaStore.MediaColumns._ID),
            "${MediaStore.MediaColumns.DISPLAY_NAME} = ? AND ${MediaStore.MediaColumns.RELATIVE_PATH} = ?",
            arrayOf(name, FOLDER),
            null,
        )?.use { if (it.moveToFirst()) ContentUris.withAppendedId(collection, it.getLong(0)) else null }
        val uri = existing ?: resolver.insert(collection, ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, FOLDER)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }) ?: throw IllegalStateException("Android could not create the file in Downloads.")
        try {
            val output = resolver.openOutputStream(uri, "wt") ?: throw IllegalStateException("Android could not open the file in Downloads.")
            output.use { it.write(bytes) }
        } catch (e: Exception) {
            if (existing == null) resolver.delete(uri, null, null)
            throw e
        }
        if (existing == null) {
            resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
        }
        // Android renames the file when another app already saved one with this name.
        val saved = resolver.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)
            ?.use { if (it.moveToFirst()) it.getString(0) else null }
        return mapOf("uri" to uri.toString(), "name" to (saved ?: name))
    }

    fun open(activity: Activity, uri: String, mime: String) {
        val target = Uri.parse(uri)
        // Only files saved above; the viewer gets read access to that one file.
        require(target.scheme == "content" && target.authority == MediaStore.AUTHORITY) { "Fieldwork only opens files it saved." }
        try {
            activity.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(target, mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        } catch (e: ActivityNotFoundException) {
            throw IllegalStateException("No app on this phone opens this file.")
        }
    }
}
