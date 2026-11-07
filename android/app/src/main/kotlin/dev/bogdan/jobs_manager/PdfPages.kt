package dev.bogdan.jobs_manager

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import java.io.ByteArrayOutputStream
import java.io.File

// Draws a PDF's pages as PNG images for the app's PDF viewer, with Android's own renderer.
object PdfPages {
    // A CV has one or two pages; this keeps a large PDF from running the phone out of memory.
    private const val MAX_PAGES = 20

    fun render(context: Context, bytes: ByteArray, width: Int): List<ByteArray> {
        require(width in 100..4096) { "The page width must be between 100 and 4096 pixels." }
        // PdfRenderer reads from a seekable file, not from memory.
        val file = File.createTempFile("view", ".pdf", context.cacheDir)
        try {
            file.writeBytes(bytes)
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
                PdfRenderer(descriptor).use { renderer ->
                    (0 until minOf(renderer.pageCount, MAX_PAGES)).map { index ->
                        renderer.openPage(index).use { page -> png(page, width) }
                    }
                }
            }
        } catch (e: SecurityException) {
            throw IllegalStateException("This PDF is password protected.")
        } catch (e: java.io.IOException) {
            throw IllegalStateException("This file is not a PDF Android can read.")
        } finally {
            file.delete()
        }
    }

    private fun png(page: PdfRenderer.Page, width: Int): ByteArray {
        val height = maxOf(1, (width.toLong() * page.height / maxOf(1, page.width)).toInt())
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        try {
            // Pages draw on a transparent bitmap; paper is white.
            bitmap.eraseColor(Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            return ByteArrayOutputStream().use { output ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
                output.toByteArray()
            }
        } finally {
            bitmap.recycle()
        }
    }
}
