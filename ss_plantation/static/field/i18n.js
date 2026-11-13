const STRINGS = {
  id: {
    app: 'Lapangan', online: 'Online', offline: 'Offline', syncNow: 'Sinkron sekarang', syncing: 'Menyinkron…',
    home: 'Beranda', tally: 'Tally Panen', attention: 'Perlu perhatian', settings: 'Pengaturan', back: 'Kembali',
    pending: 'menunggu kirim', lastSync: 'Sinkron terakhir', never: 'belum pernah', dataAge: 'Data referensi',
    pairTitle: 'Hubungkan perangkat', pairHelp: 'Masuk sekali dengan akun Odoo Anda saat ada sinyal. Setelah itu aplikasi bekerja tanpa sinyal.',
    deviceName: 'Nama perangkat', pair: 'Hubungkan', pairing: 'Menghubungkan…', signIn: 'Masuk dulu',
    needOnline: 'Perlu sinyal untuk menghubungkan perangkat.', pairFailed: 'Gagal menghubungkan.',
    loadingData: 'Mengunduh data referensi…', noData: 'Data referensi belum ada. Buka aplikasi sekali saat ada sinyal.',
    newTally: '+ Tally baru', date: 'Tanggal', division: 'Divisi', pick: '— pilih —', lines: 'Baris panen',
    addLine: 'Tambah baris', harvester: 'Pemanen', block: 'Blok', ripe: 'Matang', overripe: 'Lewat matang', unripe: 'Mentah',
    loose: 'Brondolan (kg)', add: 'Tambah', save: 'Simpan', cancel: 'Batal', remove: 'Hapus', edit: 'Ubah',
    searchHarvester: 'Cari nama atau badge…', total: 'Total janjang',
    stPending: 'Menunggu', stSynced: 'Terkirim', stRejected: 'Ditolak', empty: 'Belum ada data.',
    errHarvester: 'Pilih pemanen.', errBlock: 'Pilih blok.', errDivision: 'Pilih divisi.', errLines: 'Tambahkan minimal satu baris.',
    errNegative: 'Angka tidak boleh negatif.', errDup: 'Pemanen ini sudah dicatat di blok yang sama hari ini.',
    errCount: 'Isi jumlah janjang atau brondolan.',
    attentionHelp: 'Server menolak data ini. Perbaiki lalu kirim ulang, atau hapus.',
    resend: 'Perbaiki & kirim ulang', userLabel: 'Pengguna', version: 'Versi', refreshData: 'Perbarui data referensi',
    unpair: 'Putuskan perangkat', unpairBlocked: 'Masih ada data yang belum terkirim. Kirim dulu atau hapus.',
    unpairConfirm: 'Putuskan perangkat ini dan hapus data lokal?', language: 'Bahasa',
    warnOldPending: 'Ada data lebih dari 3 hari yang belum terkirim. Cari sinyal dan sinkronkan.',
    warnOldData: 'Data referensi sudah lebih dari 7 hari.', sessionExpired: 'Perangkat ini ditolak server. Hubungkan ulang.',
    serverError: 'Server bermasalah. Akan dicoba lagi.', updated: 'Versi baru tersedia.', reload: 'Muat ulang',
    days: 'hari', hours: 'jam', minutes: 'menit', ago: 'lalu', justNow: 'baru saja',
    transport: 'Nota Angkut', activity: 'Aktivitas Lapangan', newTransport: '+ Nota angkut baru', newActivity: '+ Aktivitas baru',
    harvestedAt: 'Jam panen', plate: 'Plat nomor', driver: 'Sopir', bunches: 'Janjang', activityType: 'Jenis aktivitas',
    quantity: 'Jumlah', palms: 'pohon', manDays: 'Hari orang', workers: 'Pekerja', addWorker: 'Tambah pekerja', note: 'Catatan',
    stockInputs: 'Input stok', addInput: 'Tambah input', product: 'Produk', qty: 'Jumlah',
    searchEmployee: 'Cari nama atau badge…', searchProduct: 'Cari produk…',
    inputsHint: 'Stok baru berkurang saat penyelia menandai aktivitas Selesai di Odoo.',
    errBunches: 'Isi jumlah janjang (bilangan bulat lebih dari 0).', errType: 'Pilih jenis aktivitas.', errProduct: 'Pilih produk.',
    errInputQty: 'Jumlah input harus lebih dari 0.',
  },
  en: {
    app: 'Field', online: 'Online', offline: 'Offline', syncNow: 'Sync now', syncing: 'Syncing…',
    home: 'Home', tally: 'Harvest Tally', attention: 'Needs attention', settings: 'Settings', back: 'Back',
    pending: 'waiting to send', lastSync: 'Last sync', never: 'never', dataAge: 'Reference data',
    pairTitle: 'Pair this device', pairHelp: 'Sign in once with your Odoo account while you have signal. After that the app works without signal.',
    deviceName: 'Device name', pair: 'Pair', pairing: 'Pairing…', signIn: 'Sign in first',
    needOnline: 'You need signal to pair this device.', pairFailed: 'Pairing failed.',
    loadingData: 'Downloading reference data…', noData: 'No reference data yet. Open the app once with signal.',
    newTally: '+ New tally', date: 'Date', division: 'Division', pick: '— select —', lines: 'Harvest lines',
    addLine: 'Add line', harvester: 'Harvester', block: 'Block', ripe: 'Ripe', overripe: 'Overripe', unripe: 'Unripe',
    loose: 'Loose fruit (kg)', add: 'Add', save: 'Save', cancel: 'Cancel', remove: 'Delete', edit: 'Edit',
    searchHarvester: 'Search name or badge…', total: 'Total bunches',
    stPending: 'Pending', stSynced: 'Sent', stRejected: 'Rejected', empty: 'Nothing yet.',
    errHarvester: 'Select a harvester.', errBlock: 'Select a block.', errDivision: 'Select a division.', errLines: 'Add at least one line.',
    errNegative: 'Numbers cannot be negative.', errDup: 'This harvester is already recorded on this block today.',
    errCount: 'Enter bunches or loose fruit.',
    attentionHelp: 'The server rejected this. Fix and resend, or delete it.',
    resend: 'Fix & resend', userLabel: 'User', version: 'Version', refreshData: 'Refresh reference data',
    unpair: 'Unpair device', unpairBlocked: 'Some entries are not sent yet. Send or delete them first.',
    unpairConfirm: 'Unpair this device and erase local data?', language: 'Language',
    warnOldPending: 'Some entries are over 3 days old and unsent. Find signal and sync.',
    warnOldData: 'Reference data is over 7 days old.', sessionExpired: 'The server rejected this device. Pair it again.',
    serverError: 'Server problem. Will retry.', updated: 'A new version is available.', reload: 'Reload',
    days: 'days', hours: 'hours', minutes: 'minutes', ago: 'ago', justNow: 'just now',
    transport: 'Transport Note', activity: 'Field Activity', newTransport: '+ New transport note', newActivity: '+ New activity',
    harvestedAt: 'Harvested at', plate: 'Plate', driver: 'Driver', bunches: 'Bunches', activityType: 'Activity type',
    quantity: 'Quantity', palms: 'palms', manDays: 'Man days', workers: 'Workers', addWorker: 'Add worker', note: 'Note',
    stockInputs: 'Stock inputs', addInput: 'Add input', product: 'Product', qty: 'Quantity',
    searchEmployee: 'Search name or badge…', searchProduct: 'Search product…',
    inputsHint: 'Stock is only used when a supervisor marks the activity Done in Odoo.',
    errBunches: 'Enter the number of bunches (a whole number above 0).', errType: 'Select an activity type.', errProduct: 'Select a product.',
    errInputQty: 'The input quantity must be above 0.',
  },
};

let lang = 'id';
export const setLang = (l) => { lang = STRINGS[l] ? l : 'id'; document.documentElement.lang = lang; };
export const getLang = () => lang;
export const t = (key) => STRINGS[lang][key] ?? STRINGS.en[key] ?? key;

export function ago(ms) {
  if (!ms) return t('never');
  const mins = Math.round((Date.now() - ms) / 60000);
  if (mins < 1) return t('justNow');
  if (mins < 60) return `${mins} ${t('minutes')} ${t('ago')}`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} ${t('hours')} ${t('ago')}`;
  return `${Math.round(hours / 24)} ${t('days')} ${t('ago')}`;
}
