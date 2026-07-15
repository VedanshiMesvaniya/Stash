// offline-queue.js
// Minimal IndexedDB queue: if a chat message fails to reach /api/chat because
// the device is offline, we can't run the LLM client-side (it's a cloud API
// call - Groq/OpenRouter - server-only), so true offline *transaction entry
// via chat* isn't possible — be upfront about that limitation. What this DOES
// support is queuing already-structured transactions (e.g. from a future
// quick-add UI) and syncing them to /api/sync once back online. Wired up but
// not auto-invoked anywhere yet since no offline quick-add UI exists in this build.

const DB_NAME = "stash_offline";
const STORE_NAME = "queued_transactions";

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function queueTransaction(txn) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).add({ ...txn, client_created_at: new Date().toISOString() });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getQueuedTransactions() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function clearQueue() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function syncQueuedTransactions() {
  const queued = await getQueuedTransactions();
  if (queued.length === 0) return { inserted: 0, skipped_duplicates: 0 };
  const res = await fetch("/api/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions: queued }),
  });
  if (res.ok) await clearQueue();
  return res.json();
}

window.addEventListener("online", () => {
  syncQueuedTransactions().catch(() => {});
});
