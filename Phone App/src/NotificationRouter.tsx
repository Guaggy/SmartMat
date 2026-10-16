import * as Notifications from "expo-notifications";
import { useRouter } from "expo-router";
import { useEffect, useRef } from "react";

// Tapping an alert push opens the Alerts tab, where the alert can be acknowledged. useLastNotificationResponse also
// covers the case where the tap started the app. Each tap is handled once.
export function NotificationRouter() {
  const router = useRouter();
  const response = Notifications.useLastNotificationResponse();
  const handled = useRef<string | null>(null);

  useEffect(() => {
    if (!response || response.actionIdentifier !== Notifications.DEFAULT_ACTION_IDENTIFIER) return;
    const id = response.notification.request.identifier;
    if (handled.current === id) return;
    handled.current = id;
    router.push("/alerts");
  }, [response, router]);

  return null;
}
