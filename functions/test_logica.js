const { MongoClient } = require('mongodb');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

async function testAllLeagues() {
    const MONGO_URI = process.env.MONGO_URI;
    const client = new MongoClient(MONGO_URI);

    const leagues = [
        { id: 'SERIE_A', name: 'Serie A' },
        { id: 'SERIE_B', name: 'Serie B' },
        { id: 'SERIE_C_A', name: 'Serie C - Girone A' },
        { id: 'SERIE_C_B', name: 'Serie C - Girone B' },
        { id: 'SERIE_C_C', name: 'Serie C - Girone C' },
        { id: 'PREMIER_LEAGUE', name: 'Premier League' },
        { id: 'LA_LIGA', name: 'La Liga' },
        { id: 'BUNDESLIGA', name: 'Bundesliga' },
        { id: 'LIGUE_1', name: 'Ligue 1' },
        { id: 'EREDIVISIE', name: 'Eredivisie' },
        { id: 'LIGA_PORTUGAL', name: 'Liga Portugal' }
    ];

    try {
        await client.connect();
        const db_name = MONGO_URI.split('/').pop()?.split('?')[0] || 'football_simulator_db';
        const db = client.db(db_name);
        const oggi = new Date();

        console.log(`\n=== TEST TOTALE CAMPIONATI (Data: ${oggi.toLocaleDateString()}) ===\n`);

        for (const league of leagues) {
            const docs = await db.collection('h2h_by_round')
                .find({ league: league.name })
                .toArray();

            if (docs.length === 0) {
                console.log(`⚠️ ${league.id}: Nessun dato nel DB.`);
                continue;
            }

            // Ordinamento numerico
            const sortedRounds = docs.sort((a, b) => {
                const getNum = (name) => parseInt(name.match(/\d+/)?.[0] || 0);
                return getNum(a.round_name) - getNum(b.round_name);
            });

            let anchorIndex = -1;

            // TUA LOGICA: Stop immediato al primo match futuro
            for (let i = 0; i < sortedRounds.length; i++) {
                const currentRound = sortedRounds[i];
                const validMatch = (currentRound.matches || []).find(m => {
                    return (m.status === 'Scheduled' || m.status === 'Timed') && new Date(m.date_obj) >= oggi;
                });

                if (validMatch) {
                    anchorIndex = i;
                    break; 
                }
            }

            if (anchorIndex !== -1) {
                const attuale = sortedRounds[anchorIndex].round_name;
                const precedente = anchorIndex > 0 ? sortedRounds[anchorIndex - 1].round_name : "---";
                const successiva = anchorIndex < sortedRounds.length - 1 ? sortedRounds[anchorIndex + 1].round_name : "---";

                console.log(`${league.id.padEnd(15)} | PREC: ${precedente.padEnd(12)} | ATT: ${attuale.padEnd(12)} | SUCC: ${successiva}`);
            } else {
                console.log(`${league.id.padEnd(15)} | ❌ Nessuna giornata attuale trovata.`);
            }
        }

    } catch (err) {
        console.error('❌ Errore:', err);
    } finally {
        await client.close();
    }
}

testAllLeagues();