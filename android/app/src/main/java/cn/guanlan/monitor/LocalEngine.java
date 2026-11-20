package cn.guanlan.monitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import android.util.Log;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

final class LocalEngine {
    private static LocalEngine instance;
    static synchronized LocalEngine get(Context context) {
        if (instance == null) instance = new LocalEngine(context.getApplicationContext());
        return instance;
    }
    final ExecutorService requests = Executors.newFixedThreadPool(3);
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private final AtomicBoolean ticking = new AtomicBoolean();
    private final Context context;
    private PyObject runtime;
    private volatile boolean visible, background;
    private volatile long nextTick;
    volatile String lastError = "", lastSync = "尚未计算";

    private LocalEngine(Context context) {
        this.context = context;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("monitor", "后台监控状态", NotificationManager.IMPORTANCE_LOW));
        manager.createNotificationChannel(new NotificationChannel("alerts", "股票 / ETF 条件报警", NotificationManager.IMPORTANCE_HIGH));
        scheduler.scheduleWithFixedDelay(this::scheduledTick, 3, 5, TimeUnit.SECONDS);
    }
    synchronized PyObject runtime() throws Exception {
        if (runtime == null) {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
            PyObject candidate = Python.getInstance().getModule("backend.android_runtime");
            candidate.callAttr("initialize", context.getFilesDir().getAbsolutePath(),
                    context.getApplicationInfo().nativeLibraryDir + "/libguanlan_talib.so");
            candidate.callAttr("configure", Credentials.read(context));
            runtime = candidate;
        }
        return runtime;
    }
    void visible(boolean value) { visible = value; }
    void background(boolean value) { background = value; }
    boolean background() { return background; }
    String request(String method, String path, String body) throws Exception {
        return runtime().callAttr("request", method, path, body).toString();
    }
    void saveCredentials(String json) throws Exception {
        runtime().callAttr("configure", json);
        Credentials.write(context, json);
    }
    void refreshSoon() { nextTick = 0; }
    private void scheduledTick() {
        if ((!visible && !background) || System.currentTimeMillis() < nextTick || !ticking.compareAndSet(false, true)) return;
        PowerManager.WakeLock wake = context.getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "guanlan:market-cycle");
        try {
            // Only held while working. This is not a workaround for Doze or force-stop.
            wake.acquire(3 * 60 * 1000L);
            JSONObject result = new JSONObject(runtime().callAttr("tick").toString());
            int interval = Math.max(60, result.optInt("interval", 60));
            nextTick = (System.currentTimeMillis() / (interval * 1000L) + 1) * interval * 1000L + 3000;
            lastError = result.optString("error", "");
            lastSync = result.optString("last_sync", lastSync);
            notifyAlerts();
        } catch (Exception e) {
            lastError = "本地监控异常，请打开应用检查数据与设置";
            Log.e("Guanlan", "Local monitor failed", e);
            nextTick = System.currentTimeMillis() + 60000;
        } finally {
            if (wake.isHeld()) wake.release();
            ticking.set(false);
        }
    }
    private void notifyAlerts() throws Exception {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (!manager.areNotificationsEnabled()) return; // Keep durable cursor until permission is granted.
        SharedPreferences prefs = context.getSharedPreferences("runtime", Context.MODE_PRIVATE);
        long cursor = prefs.getLong("notification_cursor", 0);
        JSONArray alerts = new JSONArray(runtime().callAttr("notifications", cursor).toString());
        for (int i = 0; i < alerts.length(); i++) {
            JSONObject item = alerts.getJSONObject(i);
            long id = item.getLong("id");
            String title = ("demo".equals(item.getString("source")) ? "[演示] " : "") + item.getString("rule_name");
            String text = item.getString("name") + " · " + item.getString("symbol") + "\nK线 " + item.getString("bar_time");
            Notification notification = new Notification.Builder(context, "alerts").setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(title).setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
                    .setContentIntent(open(context, "alerts")).setAutoCancel(true).setOnlyAlertOnce(true).build();
            manager.notify("signal", (int) id, notification);
            prefs.edit().putLong("notification_cursor", id).apply();
        }
    }
    static PendingIntent open(Context context, String page) {
        Intent intent = new Intent(context, MainActivity.class).putExtra("page", page)
                .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(context, page.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
