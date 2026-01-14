require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const { MongoClient } = require('mongodb');
const multer = require('multer');
const configureMulter = require('./config/multer');
const path = require('path');
const mediaRoutes = require('./routes/mediaRoutes');
const postRoutes = require('./routes/postRoutes');
const cors = require('cors');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const File = require('./models/File');
const Post = require('./models/Post');
const connectDB = require('./config/mongodb');

let app = null;
let geminiModel = null;

const initializeServer = async (expressApp) => {
  app = expressApp;

  // Configurazione base
  app.use(cors({
    origin: ['https://pup-pals.vercel.app', 'http://localhost:3000'],
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: true
  }));

  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

  // Health check
  app.get('/health', (req, res) => {
    res.status(200).json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime()
    });
  });

  // Logging middleware
  app.use((req, res, next) => {
    console.log(`=== NUOVA RICHIESTA === Metodo: ${req.method} Path: ${req.path}`);
    next();
  });

  try {
    const MONGODB_URI = process.env.MONGODB_URI;
    const mongoConnection = await connectDB(MONGODB_URI);
    // Configurazione Multer
    const { upload, saveFileToGridFS, deleteFileFromGridFS } = configureMulter(mongoConnection);
    app.set('upload', upload);
    app.set('saveFileToGridFS', saveFileToGridFS);
    app.set('deleteFileFromGridFS', deleteFileFromGridFS);

    const client = new MongoClient(MONGODB_URI);
    await client.connect();
    const db = client.db();
    const bucket = new mongoose.mongo.GridFSBucket(db, { bucketName: 'uploads' });

    app.set('mongoClient', client);
    app.set('mongoDB', db);
    app.set('bucket', bucket);

   // Configurazione Gemini
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
if (GEMINI_API_KEY) {
  const genAI = new GoogleGenerativeAI(GEMINI_API_KEY.replace(/"/g, ''));
  geminiModel = genAI.getGenerativeModel({ model: "gemini-pro" });
  app.set('geminiModel', geminiModel);
  console.log('Gemini configurato correttamente');
}

    // Rotte
    app.use('/api', mediaRoutes);
    app.use('/api/posts', postRoutes);

    // NUOVA ROTTA: Le tue 11 competizioni
app.get('/api/leagues', (req, res) => {
  const country = req.query.country;
  
  const leaguesData = {
    'Italy': [
      { id: 'SERIE_A', name: 'Serie A' },
      { id: 'SERIE_B', name: 'Serie B' },
      { id: 'SERIE_C_A', name: 'Serie C - Girone A' },
      { id: 'SERIE_C_B', name: 'Serie C - Girone B' },
      { id: 'SERIE_C_C', name: 'Serie C - Girone C' }
    ],
    'England': [{ id: 'PREMIER_LEAGUE', name: 'Premier League' }],
    'Spain': [{ id: 'LA_LIGA', name: 'La Liga' }],
    'Germany': [{ id: 'BUNDESLIGA', name: 'Bundesliga' }],
    'France': [{ id: 'LIGUE_1', name: 'Ligue 1' }],
    'Netherlands': [{ id: 'EREDIVISIE', name: 'Eredivisie' }],
    'Portugal': [{ id: 'LIGA_PORTUGAL', name: 'Liga Portugal' }]
  };

  const result = leaguesData[country] || [];
  res.json(result);
});


    // File Routes
    setupFileRoutes(app);

    // Error Handling
    setupErrorHandling(app);

    console.log('Server inizializzato con successo');
    return app;

  } catch (error) {
    console.error('Errore inizializzazione server:', error);
    throw error;
  }
};



  

const setupErrorHandling = (app) => {
  app.use((err, req, res, next) => {
    console.error('=== ERRORE ===', err);

    if (err instanceof multer.MulterError) {
      return res.status(400).json({
        success: false,
        error: 'Errore durante l\'upload del file',
        details: err.message
      });
    }

    if (err.code === 'LIMIT_FILE_SIZE') {
      return res.status(400).json({
        success: false,
        error: 'File troppo grande'
      });
    }

    res.status(500).json({
      error: 'Errore interno del server',
      message: err.message
    });
  });
};

// Gestione processo
process.on('SIGTERM', () => {
  console.log('Processo SIGTERM ricevuto. Chiusura server...');
  mongoose.connection.close(false, () => {
    console.log('Connessione MongoDB chiusa');
    process.exit(0);
  });
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Promessa non gestita:', reason);
  mongoose.connection.close(false, () => {
    process.exit(1);
  });
});

// Avvio del server solo in sviluppo locale
if (require.main === module) {
  const PORT = process.env.PORT || 8080;
  const app = express();
  initializeServer(app).then(() => {
    app.listen(PORT, () => {
      console.log(`Server in ascolto sulla porta ${PORT}`);
    });
  }).catch(error => {
    console.error('Errore durante l\'avvio del server:', error);
    process.exit(1);
  });
}

// Esportazione per Cloud Functions
module.exports = async (expressApp) => {
  try {
    return await initializeServer(expressApp);
  } catch (error) {
    console.error('Errore durante l\'inizializzazione del server:', error);
    throw error;
  }
};