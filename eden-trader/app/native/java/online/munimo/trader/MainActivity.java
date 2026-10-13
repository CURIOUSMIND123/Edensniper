package online.munimo.trader;

import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import com.getcapacitor.BridgeActivity;

/**
 * Replaces the generated MainActivity: starts the call-watching service (notifications) and, once, asks Android
 * to let the app run in the background (so the phone doesn't stop the notifications to save battery).
 */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TraderService.start(this);
        askBatteryOnce();
    }

    @Override
    public void onResume() {
        super.onResume();
        TraderService.start(this);
    }

    private void askBatteryOnce() {
        if (Build.VERSION.SDK_INT < 23) return;
        SharedPreferences sp = getSharedPreferences("trader", MODE_PRIVATE);
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (pm == null || pm.isIgnoringBatteryOptimizations(getPackageName()) || sp.getBoolean("askedBattery", false)) return;
        sp.edit().putBoolean("askedBattery", true).apply();
        try {
            startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName())));
        } catch (Exception ignored) {
            // some phones don't offer the dialog; the Settings tab explains the manual way
        }
    }
}
