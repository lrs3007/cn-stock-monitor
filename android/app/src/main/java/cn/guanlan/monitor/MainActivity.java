package cn.guanlan.monitor;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.util.LinkedHashMap;
import java.util.Map;

public final class MainActivity extends Activity {
    private static final int GREEN = Color.rgb(35, 76, 66);
    private FrameLayout content;
    private WebView web;
    private LocalEngine engine;
    private boolean settingsVisible;
    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState); engine = LocalEngine.get(this);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(244, 246, 247)); setContentView(root);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets safe = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return Build.VERSION.SDK_INT >= 30 ? WindowInsets.CONSUMED : insets.consumeSystemWindowInsets();
        });
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        LinearLayout toolbar = new LinearLayout(this); toolbar.setGravity(Gravity.CENTER_VERTICAL); toolbar.setPadding(dp(16), 0, dp(8), 0);
        toolbar.addView(text("观澜 · 独立版", 18, GREEN), new LinearLayout.LayoutParams(0, dp(48), 1));
        toolbar.addView(button("工作台", v -> restoreWorkspace())); toolbar.addView(button("运行", v -> showSettings())); root.addView(toolbar);
        content = new FrameLayout(this); root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1)); initialize();
        if (Build.VERSION.SDK_INT >= 33) getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::goBack);
    }
    private int dp(int n) { return (int) (n * getResources().getDisplayMetrics().density + .5f); }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setGravity(Gravity.CENTER_VERTICAL); view.setPadding(0, dp(8), 0, dp(8)); return view;
    }
    private Button button(String title, View.OnClickListener listener) {
        Button button = new Button(this); button.setText(title); button.setTextColor(GREEN); button.setAllCaps(false); button.setOnClickListener(listener); return button;
    }
    private LinearLayout page() {
        content.removeAllViews(); ScrollView scroll = new ScrollView(this); LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL); layout.setPadding(dp(24), dp(18), dp(24), dp(24)); scroll.addView(layout); content.addView(scroll); return layout;
    }
    private void initialize() {
        LinearLayout layout = page(); layout.addView(text("正在启动手机计算引擎…", 22, GREEN));
        layout.addView(text("首次启动需要解压运行组件。自选、规则、历史行情和报警都保存在手机中，无需电脑。", 15, Color.DKGRAY));
        engine.requests.execute(() -> {
            try { engine.runtime(); runOnUiThread(() -> { if (!isDestroyed()) openWorkspace(); }); }
            catch (Exception ex) {
                android.util.Log.e("Guanlan", "Initialization failed", ex);
                runOnUiThread(() -> {
                    if (isDestroyed()) return; LinearLayout error = page(); error.addView(text("本地引擎启动失败", 22, GREEN));
                    error.addView(text("请检查剩余空间后重试。已保存的数据会保留。\n" + ex.getClass().getSimpleName() + ": " + ex.getMessage(), 14, Color.DKGRAY));
                    error.addView(button("重试启动", v -> initialize()));
                });
            }
        });
    }
    private void showSettings() {
        settingsVisible = true; LinearLayout layout = page(); layout.addView(text("手机独立运行", 25, GREEN));
        layout.addView(text("行情采集、指标计算、规则筛选和数据库均在手机上运行。真实行情需要网络；断网保留历史并暂停新的真实信号。", 15, Color.DKGRAY));
        layout.addView(text(engine.background() ? "后台监控已开启" : "当前仅在应用前台监控", 19, GREEN));
        layout.addView(text("最近计算：" + engine.lastSync + (engine.lastError.isEmpty() ? "" : "\n" + engine.lastError), 13, Color.DKGRAY));
        String stop = getSharedPreferences("runtime", MODE_PRIVATE).getString("stop_reason", "");
        if (!stop.isEmpty()) layout.addView(text(stop, 14, Color.DKGRAY));
        layout.addView(button(engine.background() ? "停止后台监控" : "开启本次后台监控", v -> {
            if (engine.background()) { stopService(new Intent(this, MonitorService.class)); engine.background(false); showSettings(); }
            else startMonitoring();
        }));
        layout.addView(text("后台监控显示常驻通知，每次最长 5 小时 45 分；到时需打开应用再次开启。交易日午休保留会话，休市不产生新报警。重启手机、强制停止或系统清理后不会自动恢复。", 14, Color.DKGRAY));
        layout.addView(text("请在系统电池设置允许观澜后台运行。省电策略仍可能延迟分钟调度，不能保证锁屏后严格每 60 秒执行。", 14, Color.DKGRAY));
        layout.addView(button("通知权限与测试", v -> notificationTest()));
        layout.addView(button("打开系统电池设置", v -> {
            try { startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)); }
            catch (android.content.ActivityNotFoundException e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
        }));
        layout.addView(button("可选：行情密钥与邮件配置", v -> showCredentials()));
        layout.addView(button("开源许可", v -> showLicenses()));
        layout.addView(button("返回工作台", v -> restoreWorkspace()));
        layout.addView(text("观澜 0.3.1 · Android 8.0+ · ARM64\n手机与电脑分别保存数据；可在“数据与设置”迁移自选和规则。网页与 App 共用功能代码；更新需安装新版 APK。卸载会删除本机数据，请先导出规则。", 13, Color.GRAY));
    }
    private void notificationTest() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10); return;
        }
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (!manager.areNotificationsEnabled()) startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName()));
        else {
            manager.notify("test", 0, new Notification.Builder(this, "alerts").setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle("观澜 · 通知测试").setContentText("手机本地提醒已可用；这不是交易信号。")
                    .setContentIntent(LocalEngine.open(this, "alerts")).setAutoCancel(true).build());
            Toast.makeText(this, "测试通知已发送", Toast.LENGTH_SHORT).show();
        }
    }
    private void showLicenses() {
        LinearLayout layout = page(); layout.addView(text("开源组件", 24, GREEN));
        layout.addView(text("Chaquopy · Python · NumPy · Pandas · FastAPI · Pydantic · HTTPX · TA-Lib\nPython 依赖原有许可证随组件一并保留。", 14, Color.DKGRAY));
        for (String name : new String[]{"TA-Lib", "AKShare"}) {
            try (java.io.InputStream input = getAssets().open("web/licenses/" + name + ".txt")) {
                java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                layout.addView(text(name + "\n" + output.toString("UTF-8"), 12, Color.DKGRAY));
            } catch (java.io.IOException e) { layout.addView(text("许可文件读取失败", 14, Color.DKGRAY)); }
        }
        layout.addView(button("返回运行设置", v -> showSettings()));
    }
    private void startMonitoring() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 11); return;
        }
        try {
            startForegroundService(new Intent(this, MonitorService.class));
            content.postDelayed(() -> { if (!isDestroyed() && settingsVisible) showSettings(); }, 250);
        } catch (RuntimeException e) { Toast.makeText(this, "系统未允许后台启动，请稍后从应用内重试", Toast.LENGTH_LONG).show(); }
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == 11 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) startMonitoring();
        else Toast.makeText(this, "可在运行页查看通知权限；未授权时仍可查看站内报警", Toast.LENGTH_LONG).show();
    }
    private void showCredentials() {
        try {
            JSONObject existing = new JSONObject(Credentials.read(this)); LinearLayout layout = page(); layout.addView(text("可选服务配置", 24, GREEN));
            layout.addView(text("免 Token 行情无需填写。密钥由 Android Keystore 加密保存；留空并保存将清除对应字段。", 14, Color.DKGRAY));
            Map<String, EditText> fields = new LinkedHashMap<>();
            for (String key : new String[]{"TUSHARE_TOKEN", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "ALERT_EMAIL"}) {
                layout.addView(text(key, 13, GREEN)); EditText input = new EditText(this); input.setSingleLine(true);
                input.setInputType(InputType.TYPE_CLASS_TEXT | ((key.contains("TOKEN") || key.contains("PASSWORD")) ? InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD));
                input.setText(existing.optString(key)); fields.put(key, input); layout.addView(input);
            }
            layout.addView(button("加密保存配置", v -> {
                JSONObject values = new JSONObject();
                try { for (Map.Entry<String, EditText> item : fields.entrySet()) values.put(item.getKey(), item.getValue().getText().toString().trim()); }
                catch (Exception ignored) { return; }
                v.setEnabled(false); engine.requests.execute(() -> {
                    try { engine.saveCredentials(values.toString()); runOnUiThread(() -> { showSettings(); Toast.makeText(this, "已保存；可在工作台切换数据源", Toast.LENGTH_SHORT).show(); }); }
                    catch (Exception e) { runOnUiThread(() -> { v.setEnabled(true); Toast.makeText(this, "配置保存失败，请重试", Toast.LENGTH_LONG).show(); }); }
                });
            }));
            layout.addView(button("取消", v -> showSettings()));
        } catch (Exception e) { Toast.makeText(this, "无法读取本机密钥", Toast.LENGTH_LONG).show(); }
    }
    private void restoreWorkspace() {
        if (web == null) { initialize(); return; }
        settingsVisible = false; content.removeAllViews(); content.addView(web); web.onResume();
    }
    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private void openWorkspace() {
        settingsVisible = false; destroyWeb(); content.removeAllViews(); web = new WebView(this);
        WebSettings settings = web.getSettings(); settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false); settings.setAllowContentAccess(false); settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " GuanlanAndroid/0.3.1"); settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        web.addJavascriptInterface(new Bridge(web), "GuanlanNative");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return LocalOrigin.asset(request.getUrl().toString()) == null; }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String file = LocalOrigin.asset(request.getUrl().toString());
                if (file != null && "GET".equals(request.getMethod())) {
                    try {
                        String type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : file.endsWith(".svg") ? "image/svg+xml" : file.endsWith(".webmanifest") ? "application/manifest+json" : "text/html";
                        return new WebResourceResponse(type, "UTF-8", 200, "OK", Map.of("Cache-Control", "no-store", "X-Content-Type-Options", "nosniff", "Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"), getAssets().open("web/" + file));
                    } catch (Exception ignored) { /* Fail closed: never fetch an unknown URL. */ }
                }
                return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", Map.of(), new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) { destroyWeb(); initialize(); return true; }
        });
        content.addView(web); web.loadUrl(LocalOrigin.URL + ("alerts".equals(getIntent().getStringExtra("page")) ? "#alerts" : ""));
    }
    private final class Bridge {
        private final WebView owner;
        private final java.util.concurrent.atomic.AtomicInteger pending = new java.util.concurrent.atomic.AtomicInteger();
        Bridge(WebView owner) { this.owner = owner; }
        @JavascriptInterface public void request(String id, String method, String path, String body) {
            if (id == null || !id.matches("[0-9]{1,12}")) return;
            if (path == null || body == null || method == null || path.length() > 8192 || body.length() > 131072) { respond(id, "{\"status\":400,\"body\":{\"detail\":\"请求过大\"}}"); return; }
            if (pending.incrementAndGet() > 24) { pending.decrementAndGet(); respond(id, "{\"status\":429,\"body\":{\"detail\":\"操作繁忙，请稍后重试\"}}"); return; }
            engine.requests.execute(() -> {
                String result;
                try { result = engine.request(method, path, body); }
                catch (Exception ex) { result = "{\"status\":500,\"body\":{\"detail\":\"本地引擎暂时不可用，请重新打开应用\"}}"; }
                finally { pending.decrementAndGet(); }
                respond(id, result);
            });
        }
        private void respond(String id, String result) {
            runOnUiThread(() -> { if (!isDestroyed() && web == owner) owner.evaluateJavascript("window.guanlanResponse(" + JSONObject.quote(id) + "," + JSONObject.quote(result) + ")", null); });
        }
        @JavascriptInterface public void settings() { runOnUiThread(() -> { if (!isDestroyed()) showSettings(); }); }
        @JavascriptInterface public void copy(String value) {
            if (value != null && value.length() <= 131072) runOnUiThread(() -> getSystemService(ClipboardManager.class).setPrimaryClip(ClipData.newPlainText("观澜自选规则", value)));
        }
    }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent); setIntent(intent);
        if (web != null && "alerts".equals(intent.getStringExtra("page"))) { restoreWorkspace(); web.evaluateJavascript("location.hash='alerts'", null); }
    }
    private void goBack() {
        if (settingsVisible) { restoreWorkspace(); return; }
        if (web != null) web.evaluateJavascript("(()=>{const d=document.querySelector('dialog[open]');if(d){d.close();return true;}return false;})()", closed -> {
            if (!"true".equals(closed)) { if (web != null && web.canGoBack()) web.goBack(); else moveTaskToBack(true); }
        }); else moveTaskToBack(true);
    }
    @SuppressLint("GestureBackNavigation") @SuppressWarnings("deprecation")
    @Override public void onBackPressed() { if (Build.VERSION.SDK_INT < 33) goBack(); }
    @Override protected void onPause() { engine.visible(false); if (web != null) web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (engine != null) engine.visible(true); if (web != null) web.onResume(); }
    private void destroyWeb() {
        if (web != null) { if (web.getParent() instanceof FrameLayout) ((FrameLayout) web.getParent()).removeView(web); web.removeJavascriptInterface("GuanlanNative"); web.destroy(); web = null; }
    }
    @Override protected void onDestroy() { destroyWeb(); super.onDestroy(); }
}
