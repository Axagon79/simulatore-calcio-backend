const mongoose = require('mongoose');

const connectDB = async () => {
  try {
    // Cerca la stringa di connessione nelle variabili d'ambiente
    const uri = process.env.MONGO_URI;

    if (!uri) {
        throw new Error("MONGO_URI non definita nel file .env");
    }

    const conn = await mongoose.connect(uri);

    console.log(`MongoDB Connesso: ${conn.connection.host}`);
    return conn;
  } catch (error) {
    console.error('Errore di connessione MongoDB:', error.message);
    // Importante: in caso di errore grave all'avvio, meglio fermare il processo se siamo in locale, 
    // ma su Firebase Functions gestiamo l'errore diversamente. Per ora va bene il log.
    throw error;
  }
};

module.exports = connectDB;
