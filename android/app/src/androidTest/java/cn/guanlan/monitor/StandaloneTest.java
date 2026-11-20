package cn.guanlan.monitor;

import android.test.InstrumentationTestCase;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/** Runs on a real ARM64 Android runtime with the packaged libraries, without a desktop server. */
@SuppressWarnings("deprecation")
public class StandaloneTest extends InstrumentationTestCase {
    public void testForegroundSession() throws Exception {
        android.content.Context context = getInstrumentation().getTargetContext();
        LocalEngine engine = LocalEngine.get(context);
        android.content.Intent intent = new android.content.Intent(context, MonitorService.class);
        context.startForegroundService(intent);
        try {
            for (int i=0; i<30 && !engine.background(); i++) Thread.sleep(100);
            assertTrue("Foreground monitor started", engine.background());
            android.app.NotificationManager manager = context.getSystemService(android.app.NotificationManager.class);
            assertTrue("Persistent monitor notification", manager.getActiveNotifications().length > 0);
        } finally { context.stopService(intent); }
        for (int i=0; i<30 && engine.background(); i++) Thread.sleep(100);
        assertFalse("Stopping service stops background scheduling", engine.background());
    }
    public void testIndependentEngine() throws Exception {
        android.content.Context context = getInstrumentation().getTargetContext();
        LocalEngine engine = LocalEngine.get(context);
        engine.runtime();
        File script = new File(context.getCacheDir(), "android_smoke.py");
        try (InputStream input = getInstrumentation().getContext().getAssets().open("android_smoke.py");
             FileOutputStream output = new FileOutputStream(script)) {
            byte[] data = new byte[8192]; int count;
            while ((count = input.read(data)) != -1) output.write(data, 0, count);
        }
        PyObject result = Python.getInstance().getModule("runpy").callAttr("run_path", script.getAbsolutePath());
        assertTrue(result.callAttr("__getitem__", "SUCCESS").toBoolean());
        Credentials.write(context, "{\"SMTP_HOST\":\"example.test\"}");
        assertTrue(Credentials.read(context).contains("example.test"));
        Credentials.write(context, "{}");
    }
}
