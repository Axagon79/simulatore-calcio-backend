const express = require('express');
const router = express.Router();

// Mapping codice frontend → nome DB classifiche
const LEAGUE_MAP = {
  'SERIE_A': 'Serie A',
  'SERIE_B': 'Serie B',
  'SERIE_C_GIRONE_A': 'Serie C - Girone A',
  'SERIE_C_GIRONE_B': 'Serie C - Girone B',
  'SERIE_C_GIRONE_C': 'Serie C - Girone C',
  'PREMIER_LEAGUE': 'Premier League',
  'LA_LIGA': 'La Liga',
  'BUNDESLIGA': 'Bundesliga',
  'LIGUE_1': 'Ligue 1',
  'EREDIVISIE': 'Eredivisie',
  'LIGA_PORTUGAL': 'Liga Portugal',
  'CHAMPIONSHIP': 'Championship',
  'LA_LIGA_2': 'LaLiga 2',
  'BUNDESLIGA_2': '2. Bundesliga',
  'LIGUE_2': 'Ligue 2',
  'SCOTTISH_PREMIERSHIP': 'Scottish Premiership',
  'ALLSVENSKAN': 'Allsvenskan',
  'ELITESERIEN': 'Eliteserien',
  'SUPERLIGAEN': 'Superligaen',
  'JUPILER_PRO_LEAGUE': 'Jupiler Pro League',
  'SUPER_LIG': 'Süper Lig',
  'LEAGUE_OF_IRELAND': 'League of Ireland Premier Division',
  'BRASILEIRAO': 'Brasileirão Serie A',
  'PRIMERA_DIVISION_ARG': 'Primera División',
  'MLS': 'Major League Soccer',
  'J1_LEAGUE': 'J1 League',
};

// GET /standings/:league — classifica completa (totale + casa + trasferta)
router.get('/:league', async (req, res) => {
  try {
    const leagueName = LEAGUE_MAP[req.params.league] || req.params.league;
    const doc = await req.db.collection('classifiche').findOne({ league: leagueName });
    if (!doc) return res.json({ success: false, message: 'Classifica non trovata' });
    res.json({
      success: true,
      league: doc.league,
      country: doc.country,
      table: doc.table || [],
      table_home: doc.table_home || [],
      table_away: doc.table_away || [],
      last_updated: doc.last_updated
    });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
