package cn.guanlan.monitor;
import android.test.InstrumentationTestCase;
import com.chaquo.python.Python;
import java.io.*;
@SuppressWarnings("deprecation")
public class NetworkProbe extends InstrumentationTestCase {
    public void testPublicHttps() throws Exception {
        android.content.Context context = getInstrumentation().getTargetContext();
        LocalEngine.get(context).runtime();
        File file = new File(context.getCacheDir(), "android_network_probe.py");
        try (InputStream input = getInstrumentation().getContext().getAssets().open("android_network_probe.py"); FileOutputStream out = new FileOutputStream(file)) {
            byte[] buffer = new byte[8192]; int n; while ((n=input.read(buffer))!=-1) out.write(buffer,0,n);
        }
        String result = Python.getInstance().getModule("runpy").callAttr("run_path",file.getAbsolutePath()).callAttr("__getitem__","RESULT").toString();
        android.util.Log.i("GuanlanProbe",result);
        // Optional live check, separate from deterministic tests. Its failure
        // must stay visible rather than treating any JSON response as success.
        org.json.JSONObject report = new org.json.JSONObject(result);
        assertFalse(result, report.has("error"));
        org.json.JSONArray rows = report.getJSONArray("results");
        assertEquals(2, rows.length());
        for (int i=0; i<rows.length(); i++) {
            org.json.JSONObject row = rows.getJSONObject(i);
            assertTrue(result, row.getBoolean("current"));
            assertTrue(result, row.getBoolean("daily_macd_ready"));
            assertTrue(row.getInt("daily_rows") > 100);
            assertEquals(0, row.getJSONArray("issues").length());
        }
    }
}
