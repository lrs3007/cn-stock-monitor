package cn.guanlan.monitor;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;

/** Explicit user-started session, capped below Android 15's six-hour dataSync budget. */
public final class MonitorService extends Service {
    static final String STOP = "cn.guanlan.monitor.STOP";
    private final Handler handler = new Handler(android.os.Looper.getMainLooper());
    private final Runnable deadline = () -> stopSession("本次后台监控已到时；重新打开应用可继续");
    private boolean started;
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && STOP.equals(intent.getAction())) { stopSession("你已停止后台监控"); return START_NOT_STICKY; }
        if (started) return START_NOT_STICKY;
        Intent stop = new Intent(this, MonitorService.class).setAction(STOP);
        Notification notification = new Notification.Builder(this, "monitor")
                .setSmallIcon(R.drawable.ic_notification).setContentTitle("观澜 · 手机独立监控中")
                .setContentText("按设置间隔检查；交易时间内产生报警。本次最长 5 小时 45 分。")
                .setContentIntent(LocalEngine.open(this, "dashboard")).setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "停止监控", PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE)).build()).build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(1, notification);
        started = true;
        getSharedPreferences("runtime", MODE_PRIVATE).edit().putString("stop_reason", "").apply();
        LocalEngine.get(this).background(true);
        handler.postDelayed(deadline, 345 * 60 * 1000L);
        return START_NOT_STICKY;
    }
    private void stopSession(String reason) {
        getSharedPreferences("runtime", MODE_PRIVATE).edit().putString("stop_reason", reason).apply();
        LocalEngine.get(this).background(false);
        stopForeground(STOP_FOREGROUND_REMOVE); stopSelf();
    }
    @Override public void onTimeout(int startId, int fgsType) { stopSession("Android 已结束本次后台监控；打开应用可继续"); }
    @Override public void onDestroy() {
        handler.removeCallbacks(deadline); LocalEngine.get(this).background(false); super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
