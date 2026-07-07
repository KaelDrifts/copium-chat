// Right-click a selected CA on any page -> "Scan with COPIUM" -> opens the popup pre-filled.

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "copium-scan",
    title: 'Scan "%s" with COPIUM',
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "copium-scan" || !info.selectionText) return;
  await chrome.storage.session.set({ pendingScan: info.selectionText.trim() });
  try {
    await chrome.action.openPopup();
  } catch (e) {
    // Older Chrome versions can't open the popup programmatically;
    // the pending CA will be scanned next time the user clicks the icon.
  }
});
