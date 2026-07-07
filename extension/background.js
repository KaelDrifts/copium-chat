// Right-click a selected CA on any page -> "Scan with HOOPIUM" -> opens the popup pre-filled.

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "hoopium-scan",
    title: 'Scan "%s" with HOOPIUM',
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "hoopium-scan" || !info.selectionText) return;
  await chrome.storage.session.set({ pendingScan: info.selectionText.trim() });
  try {
    await chrome.action.openPopup();
  } catch (e) {
    // Older Chrome versions can't open the popup programmatically;
    // the pending CA will be scanned next time the user clicks the icon.
  }
});
