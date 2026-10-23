function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var expected = PropertiesService.getScriptProperties().getProperty("SECRET");
    if (!expected || data.secret !== expected) {
      return ContentService.createTextOutput("unauthorized");
    }
    GmailApp.sendEmail(data.to, data.subject, data.text || "", {
      htmlBody: data.html || data.text || "",
      name: data.from_name || "FP Mart",
      replyTo: data.from || Session.getActiveUser().getEmail(),
    });
    return ContentService.createTextOutput("ok");
  } catch (err) {
    return ContentService.createTextOutput("error: " + err);
  }
}
