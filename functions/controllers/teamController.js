const Team = require('../models/Team');

// @desc    Ottieni tutte le squadre
// @route   GET /api/teams
// @access  Public
exports.getTeams = async (req, res) => {
  try {
    const teams = await Team.find();
    
    res.status(200).json({
      success: true,
      count: teams.length,
      data: teams
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Errore del server durante il recupero delle squadre'
    });
  }
};

// @desc    Crea una nuova squadra
// @route   POST /api/teams
// @access  Public (in futuro Private/Admin)
exports.createTeam = async (req, res) => {
  try {
    // Creiamo la squadra usando i dati inviati nel body della richiesta
    const team = await Team.create(req.body);

    res.status(201).json({
      success: true,
      data: team
    });
  } catch (error) {
    // Gestione duplicati (es. squadra già esistente)
    if (error.code === 11000) {
      return res.status(400).json({
        success: false,
        error: 'Questa squadra esiste già'
      });
    }
    
    // Gestione errori di validazione (es. manca il nome o la lega)
    if (error.name === 'ValidationError') {
      const messages = Object.values(error.errors).map(val => val.message);
      return res.status(400).json({
        success: false,
        error: messages
      });
    }

    res.status(500).json({
      success: false,
      error: 'Errore del server'
    });
  }
};
