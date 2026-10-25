/** First run: no server address saved yet, once settings have been loaded. The tabs layout sends the user to Settings
 *  exactly once (a one-time router.replace in an effect, never a rendered <Redirect>, which looped on SDK 57). */
export function shouldGoToSetup(ready: boolean, serverUrl: string, alreadySent: boolean): boolean {
  return ready && !serverUrl && !alreadySent;
}
