// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The session language wins; the browser is only a fallback before a PIN is known.
export const languageTag = (value) => String(value || "en").toLowerCase().split("-")[0] === "de" ? "de" : "en";

export function phoneLabels(language) {
  return languageTag(language) === "de" ? {
  pin: "Spiel-PIN", nick: "Dein Spitzname", join: "Mitspielen", in: "Du bist dabei!", watch: "Schau nach vorne – gleich geht es los.",
  ready: "Gleich geht's los!", send: "Abschicken", sent: "Antwort abgeschickt", waitOthers: "Warte auf die anderen …",
  timesUp: "Die Zeit ist um", noAnswer: "Keine Antwort", correct: "Richtig!", wrong: "Leider falsch", partly: "Teilweise richtig",
  thanks: "Danke!", points: "Punkte", streak: "Serie", rank: (r, n) => `Platz ${r} von ${n}`, paused: "Pausiert",
  finished: "Spielende", yourRank: "Dein Platz", again: "Neu beitreten", gameOver: "Dieses Spiel ist vorbei.",
  kicked: "Du wurdest aus dem Spiel entfernt.", offline: "Verbindung wird wiederhergestellt …", typeHere: "Deine Antwort",
  several: "Mehrere Antworten können richtig sein", tickAll: "Alles Zutreffende ankreuzen",
  orderHint: "In die richtige Reihenfolge bringen", practice: "Übungsrunde – ohne Punkte",
  answerWas: "Richtige Antwort", up: "nach oben", down: "nach unten", bonus: "Serienbonus",
  answer: "Antwort", questionPicture: "Die Frage, wie vorne gezeigt",
  waitReveal: "Gleich kommt die Auflösung …", reading: "Lies die Frage – gleich kommen die Antworten.",
  draw: "Zeichne mit dem Finger.", undo: "Rückgängig", clear: "Löschen", pens: ["Schwarz", "Rot", "Blau", "Grün"],
  tooMuch: "Zu viel gezeichnet – nimm ein paar Striche zurück.", quizTab: "Quiz", qaTab: "Fragen",
  ask: "Stell eine Frage – anonym.", yourQuestion: "Deine Frage", askSend: "Fragen", noQuestions: "Noch keine Fragen.",
  yours: "deine", answered: "beantwortet", upvote: "Diese Frage unterstützen", asked: "Deine Frage ist da.",
} : {
  pin: "Game PIN", nick: "Your nickname", join: "Join", in: "You're in!", watch: "Watch the screen – it starts soon.",
  ready: "Get ready!", send: "Submit", sent: "Answer sent", waitOthers: "Waiting for the others …",
  timesUp: "Time's up", noAnswer: "No answer", correct: "Correct!", wrong: "Not quite", partly: "Partly right",
  thanks: "Thanks!", points: "points", streak: "streak", rank: (r, n) => `Rank ${r} of ${n}`, paused: "Paused",
  finished: "Game over", yourRank: "Your rank", again: "Join again", gameOver: "This game is over.",
  kicked: "You have been removed from the game.", offline: "Reconnecting …", typeHere: "Your answer",
  several: "Several answers can be correct", tickAll: "Tick all that apply",
  orderHint: "Put them in the right order", practice: "Practice round – no points",
  answerWas: "Right answer", up: "up", down: "down", bonus: "streak bonus",
  answer: "Answer", questionPicture: "The question, as shown at the front",
  waitReveal: "The answer comes next …", reading: "Read the question – the answers come next.",
  draw: "Draw with your finger.", undo: "Undo", clear: "Clear", pens: ["black", "red", "blue", "green"],
  tooMuch: "Too much drawn – undo a few strokes.", quizTab: "Quiz", qaTab: "Questions",
  ask: "Ask a question – anonymously.", yourQuestion: "Your question", askSend: "Ask", noQuestions: "No questions yet.",
  yours: "yours", answered: "answered", upvote: "Upvote this question", asked: "Your question is in.",
};
}


// Human-facing protocol failures; engine/parser diagnostics remain technical.
const ERRORS = {
  "unknown-pin": ["Zu dieser PIN gibt es kein laufendes Spiel.", "There is no active game with this PIN."],
  "nickname": ["Bitte gib einen Spitznamen mit 1 bis 20 Zeichen ein.", "Enter a nickname with 1 to 20 characters."],
  "nickname-taken": ["Dieser Spitzname ist bereits vergeben.", "This nickname is already taken."],
  "full": ["Das Spiel ist bereits voll.", "This game is full."],
  "too-many-attempts": ["Zu viele falsche PINs. Bitte versuche es in einigen Minuten erneut.", "Too many wrong PINs. Try again in a few minutes."],
  "unknown-player": ["Bitte tritt dem Spiel erneut bei.", "Please join the game again."],
  "no-session": ["Dieses Spiel ist vorbei.", "This game is over."],
  "kicked": ["Du wurdest aus dem Spiel entfernt.", "You have been removed from the game."],
  "not-open": ["Die Frage ist noch nicht geöffnet.", "The question is not open yet."],
  "closed": ["Die Antwortzeit ist abgelaufen.", "Time is up."],
  "paused": ["Die Frage ist pausiert.", "The question is paused."],
  "already-answered": ["Du hast bereits geantwortet.", "You have already answered."],
  "invalid": ["Bitte überprüfe deine Eingabe.", "Please check your input."],
};
export function phoneError(error, language) {
  const german = languageTag(language) === "de";
  const known = ERRORS[error?.code];
  if (known) return known[german ? 0 : 1];
  return german ? "Die Aktion konnte nicht ausgeführt werden. Bitte versuche es erneut."
    : error?.message || "The action could not be completed. Please try again.";
}
