const firebaseAdmin = require('../config/firebaseAdmin');

/**
 * Middleware auth opzionale: se il token è presente lo verifica,
 * altrimenti prosegue con req.userId = null.
 * Utile per endpoint che funzionano sia con che senza autenticazione.
 */
const optionalAuth = async (req, res, next) => {
  const authHeader = req.headers.authorization;

  if (authHeader && authHeader.startsWith('Bearer ')) {
    const idToken = authHeader.split('Bearer ')[1];
    try {
      const decodedToken = await firebaseAdmin.auth().verifyIdToken(idToken);
      req.userId = decodedToken.uid;
      req.userEmail = decodedToken.email || null;
    } catch (error) {
      // Token non valido — prosegui come utente anonimo
      req.userId = null;
      req.userEmail = null;
    }
  } else {
    req.userId = null;
    req.userEmail = null;
  }

  next();
};

module.exports = optionalAuth;
