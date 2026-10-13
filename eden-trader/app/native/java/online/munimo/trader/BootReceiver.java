package online.munimo.trader;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Starts the call-watching service again after the phone restarts. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        TraderService.start(context);
    }
}
