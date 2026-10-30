/**
 * Feedback relay for Command Vault (and any app using feedback.py).
 *
 * Setup (once, signed in as support.somore100@gmail.com):
 *  1. script.google.com -> New project -> paste this file.
 *  2. Set TOKEN below to a long random string (and the same value as
 *     FEEDBACK_RELAY_TOKEN in cmdvault/config.py).
 *  3. Deploy -> New deployment -> type "Web app"; Execute as: Me;
 *     Who has access: Anyone. Authorize when asked.
 *  4. Copy the web-app URL into FEEDBACK_RELAY_URL in cmdvault/config.py.
 *
 * The Gmail login never leaves Google: the app only knows the URL + token.
 * The token is not a strong secret (it ships in the app), so this script also
 * limits sizes and the number of mails per hour.
 */
var TOKEN = "CHANGE-ME";
var TO = "support.somore100@gmail.com";
var MAX_PER_HOUR = 30;

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.token !== TOKEN) return out({ ok: false, error: "bad token" });
    var subject = String(data.subject || "").slice(0, 200);
    var body = String(data.body || "").slice(0, 12000);
    if (!subject || !body) return out({ ok: false, error: "empty report" });

    var props = PropertiesService.getScriptProperties();
    var hour = Math.floor(Date.now() / 3600000);
    var key = "count_" + hour;
    var count = Number(props.getProperty(key) || 0);
    if (count >= MAX_PER_HOUR) return out({ ok: false, error: "too many reports, try later" });
    props.setProperty(key, String(count + 1));

    MailApp.sendEmail(TO, subject, body);
    return out({ ok: true });
  } catch (err) {
    return out({ ok: false, error: "bad request" });
  }
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
