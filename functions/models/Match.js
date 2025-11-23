const mongoose = require('mongoose');

const MatchSchema = new mongoose.Schema({
  // Collegamenti alle squadre (ID univoci)
  homeTeam: { 
    type: mongoose.Schema.Types.ObjectId, 
    ref: 'Team', 
    required: true 
  },
  awayTeam: { 
    type: mongoose.Schema.Types.ObjectId, 
    ref: 'Team', 
    required: true 
  },

  // Dati Campionato
  league: { type: String, required: true },
  round: { type: String }, // Es. "Giornata 13"
  date: { type: Date, required: true },

  // Stato partita
  status: { 
    type: String, 
    enum: ['SCHEDULED', 'FINISHED', 'LIVE'], 
    default: 'SCHEDULED' 
  },

  // Quote (Fondamentali per fattore BVS)
  odds: {
    one: { type: Number }, // Quota 1
    x: { type: Number },   // Quota X
    two: { type: Number }, // Quota 2
    under25: { type: Number },
    over25: { type: Number }
  },

  // Risultato reale (se giocata)
  score: {
    home: { type: Number, default: null },
    away: { type: Number, default: null }
  },

  // Qui salveremo la SIMULAZIONE della nostra AI (il pronostico)
  aiPrediction: {
    type: mongoose.Schema.Types.Mixed // Flessibile, ci mettiamo quello che vogliamo dopo
  },

  updatedAt: { type: Date, default: Date.now }
});

module.exports = mongoose.model('Match', MatchSchema);
