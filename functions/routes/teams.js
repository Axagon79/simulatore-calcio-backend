const express = require('express');
const router = express.Router();
const { getTeams, createTeam } = require('../controllers/teamController');

// Rotta base: /api/teams
router.route('/')
  .get(getTeams)    // GET serve per leggere le squadre
  .post(createTeam); // POST serve per creare una squadra

module.exports = router;
