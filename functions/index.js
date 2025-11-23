const functions = require('firebase-functions');
const express = require('express');
const cors = require('cors');
const connectDB = require('./config/db');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });


// Inizializza l'app Express
const app = express();

// Connetti al Database
connectDB();

// Middleware
app.use(cors({ origin: true })); // Abilita CORS per tutte le richieste
app.use(express.json()); // Permette di leggere i JSON inviati dal frontend

// === ROTTE ===
// Qui colleghiamo il file teams.js che hai appena creato
const teamsRouter = require('./routes/teams');

// Usa le rotte
app.use('/api/teams', teamsRouter);


// Rotta di benvenuto (per testare se il server è vivo)
app.get('/', (req, res) => {
  res.send('Simulatore Calcio API is running...');
});


// Esporta l'app come funzione Firebase
exports.api = functions.https.onRequest(app);
