const admin = require('firebase-admin');

// In Firebase Functions, admin si inizializza senza credenziali
// (usa automaticamente il service account del progetto)
if (!admin.apps.length) {
  admin.initializeApp();
}

module.exports = admin;
