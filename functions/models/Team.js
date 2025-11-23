const mongoose = require('mongoose');

const TeamSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true,
    unique: true,
    trim: true
  },
  league: {
    type: String,
    required: true,
    enum: ['Serie A', 'Serie B', 'Serie C - Girone A', 'Serie C - Girone B', 'Serie C - Girone C', 'Premier League', 'Bundesliga', 'La Liga', 'Ligue 1', 'Eredivisie', 'Liga Portugal']
  },
  country: {
    type: String,
    default: 'Italia'
  },
  logoUrl: String,
  
  // --- FATTORI STATISTICI (Per Algoritmo v3.0) ---
  
  // 4.1 LUCIFERO (Forma ponderata ultime 6)
  form: {
    last6: [{ type: String, enum: ['W', 'D', 'L'] }], // Es. ['W', 'W', 'D', 'L', 'W', 'W']
    score: { type: Number, default: 50 } // Punteggio calcolato (0-100)
  },

  // 4.3 COEFFICIENTI GOL (Stagionali + Ultime 10)
  stats: {
    goalsScoredHome: { type: Number, default: 0 },
    goalsConcededHome: { type: Number, default: 0 },
    goalsScoredAway: { type: Number, default: 0 },
    goalsConcededAway: { type: Number, default: 0 },
    matchesPlayed: { type: Number, default: 0 }
  },

  // 4.7 VALORE ROSA (Transfermarkt)
  marketValue: {
    type: Number, // In milioni di euro
    default: 0
  },

  // 4.6 MOTIVAZIONE (Classifica e Obiettivi)
  standings: {
    position: { type: Number, default: 0 },
    points: { type: Number, default: 0 }
  },
  
  updatedAt: { type: Date, default: Date.now }
});

module.exports = mongoose.model('Team', TeamSchema);
