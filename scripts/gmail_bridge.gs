function jsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return jsonResponse({
    status: "active",
    message: "UMII Email Bridge is online!"
  });
}

function authorizeGmail() {
  GmailApp.getAliases();
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({status: "error", message: "Missing request body"});
    }

    var data = JSON.parse(e.postData.contents);
    var expected = PropertiesService.getScriptProperties().getProperty("SECRET");
    if (!expected || data.secret !== expected) {
      return jsonResponse({status: "unauthorized"});
    }
    if (!data.to || !data.subject) {
      return jsonResponse({status: "error", message: "Recipient and subject are required"});
    }

    var options = {
      htmlBody: data.html || data.text || "",
      name: data.from_name || "UMII"
    };
    if (data.from) {
      options.replyTo = data.from;
    }

    GmailApp.sendEmail(data.to, data.subject, data.text || "", options);
    return jsonResponse({status: "sent"});
  } catch (err) {
    console.error(err);
    return jsonResponse({status: "error", message: String(err)});
  }
}
