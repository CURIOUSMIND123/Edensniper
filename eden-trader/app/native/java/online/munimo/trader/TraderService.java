package online.munimo.trader;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.Calendar;
import java.util.TimeZone;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Watches the trading server for new alerts and shows each as a notification, also when the app is closed.
 * Every 10 seconds on weekdays from 8:40 to 15:45 IST (the plan comes at 8:45, the day's result after 15:30),
 * every 5 minutes otherwise. Reads the server and key the app saved (Capacitor Preferences = "CapacitorStorage").
 * Runs as a foreground service (Android keeps those alive) with a quiet "watching" notification.
 */
public class TraderService extends Service {
    static final String CH_CALLS = "calls";
    static final String CH_WATCH = "watch";
    static final int ID_WATCH = 1;

    private volatile boolean running;
    private Thread worker;
    private PowerManager.WakeLock wake;

    public static void start(Context c) {
        Intent i = new Intent(c, TraderService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Exception ignored) {
            // not allowed right now (e.g. started from the background); the next app start or boot tries again
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        channels();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification n = watchNotification("Watching NIFTY and SENSEX calls");
        if (Build.VERSION.SDK_INT >= 34) startForeground(ID_WATCH, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(ID_WATCH, n);
        if (worker == null || !worker.isAlive()) {
            running = true;
            worker = new Thread(this::loop, "trader-watch");
            worker.start();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (worker != null) worker.interrupt();
        setWake(false);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void loop() {
        while (running) {
            boolean market = inMarketWindow();
            setWake(market);
            long wait;
            try {
                poll();
                wait = market ? 10_000L : 300_000L;
            } catch (Exception e) {
                wait = market ? 20_000L : 300_000L;
            }
            try {
                Thread.sleep(wait);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    private static boolean inMarketWindow() {
        Calendar c = Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"));
        int dow = c.get(Calendar.DAY_OF_WEEK);
        if (dow == Calendar.SATURDAY || dow == Calendar.SUNDAY) return false;
        int m = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        return m >= 8 * 60 + 40 && m <= 15 * 60 + 45;
    }

    private void setWake(boolean on) {
        try {
            if (on && wake == null) {
                PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
                wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "edentrader:watch");
                wake.acquire(8L * 60 * 60 * 1000);
            } else if (!on && wake != null) {
                if (wake.isHeld()) wake.release();
                wake = null;
            }
        } catch (Exception ignored) {
        }
    }

    private void poll() throws Exception {
        SharedPreferences cap = getSharedPreferences("CapacitorStorage", MODE_PRIVATE);
        String server = cap.getString("server", "");
        String key = cap.getString("key", "");
        if (server.isEmpty() || key.isEmpty()) return;
        SharedPreferences sp = getSharedPreferences("trader", MODE_PRIVATE);
        String who = server + "|" + key;
        long since = who.equals(sp.getString("who", "")) ? sp.getLong("since", -1L) : -1L;

        String url = server.replaceAll("/+$", "") + "/api/events?since=" + Math.max(since, 0L) + "&key=" + URLEncoder.encode(key, "UTF-8");
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(10_000);
        con.setReadTimeout(15_000);
        try {
            if (con.getResponseCode() != 200) return;
            StringBuilder body = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(con.getInputStream(), "UTF-8"))) {
                String line;
                while ((line = r.readLine()) != null) body.append(line);
            }
            JSONObject j = new JSONObject(body.toString());
            long last = j.optLong("last", 0L);
            if (since < 0 || last < since) {                 // first time (or the server's list was reset): start from now
                sp.edit().putString("who", who).putLong("since", last).apply();
                return;
            }
            JSONArray ev = j.optJSONArray("events");
            long max = since;
            for (int k = 0; ev != null && k < ev.length(); k++) {
                JSONObject e = ev.getJSONObject(k);
                long id = e.optLong("id", 0L);
                if (id <= since) continue;
                show(e.optString("title", "Eden Trader"), e.optString("text", ""), (int) (id % 1_000_000_000L));
                max = Math.max(max, id);
            }
            if (max > since) sp.edit().putString("who", who).putLong("since", max).apply();
        } finally {
            con.disconnect();
        }
    }

    private PendingIntent openApp() {
        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (open == null) open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private Notification.Builder builder(String channel) {
        return Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, channel) : new Notification.Builder(this);
    }

    private Notification watchNotification(String text) {
        return builder(CH_WATCH)
            .setSmallIcon(R.drawable.ic_stat_trader)
            .setContentTitle("Eden Trader")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openApp())
            .build();
    }

    private void show(String title, String text, int id) {
        Notification.Builder b = builder(CH_CALLS)
            .setSmallIcon(R.drawable.ic_stat_trader)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(new Notification.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(openApp());
        if (Build.VERSION.SDK_INT < 26) b.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.notify(id, b.build());
    }

    private void channels() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel calls = new NotificationChannel(CH_CALLS, "Buy / sell calls", NotificationManager.IMPORTANCE_HIGH);
        calls.setDescription("Every call: entry, book half, exit, the morning plan and the day's result");
        calls.enableVibration(true);
        nm.createNotificationChannel(calls);
        NotificationChannel watch = new NotificationChannel(CH_WATCH, "Watching the market", NotificationManager.IMPORTANCE_LOW);
        watch.setShowBadge(false);
        nm.createNotificationChannel(watch);
    }
}
