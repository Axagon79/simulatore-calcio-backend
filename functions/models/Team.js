const mongoose = require('mongoose');

const TeamSchema = new mongoose.Schema({
  name: {
    type: String,
    required: [true, 'Il nome della squadra è obbligatorio'],
    trim: true,
    unique: true
  },
  league: {
    type: String,
    required: true,
    enum: ['Serie A', 'Serie B', 'Serie C - Girone A', 'Serie C - Girone B', 'Serie C - Girone C', 'Premier League', 'Bundesliga', 'La Liga', 'Ligue 1', 'Eredivisie', 'Liga Portugal']
  },
  country: {
    type: String,
    required: true,
    default: 'Italia'
  },
  // Valori tecnici (da 0 a 100) per la simulazione
  stats: {
    attack: { type: Number, default: 50 },
    defense: { type: Number, default: 50 },
    midfield: { type: Number, default: 50 },
    overall: { type: Number, default: 50 }
  },
  // URL del logo (opzionale per ora)
  logoUrl: {
    type: String,
    default: ''
  },
  createdAt: {
    type: Date,
    default: Date.now
  }
});

module.exports = mongoose.model('Team', TeamSchema);

