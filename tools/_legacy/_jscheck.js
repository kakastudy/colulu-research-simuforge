const fs = require("fs");
const s = fs.readFileSync("platform/app.js", "utf8");
try {
  new Function(s);
  console.log("app.js syntax OK (" + s.length + " chars)");
} catch (e) {
  console.log("JS ERROR: " + e.message);
  process.exit(1);
}
const d = fs.readFileSync("platform/data.js", "utf8");
const m = d.match(/contract:\s*"([^"]*)"/);
console.log("data.js contract:", m ? m[1] : "(not found)");
const g = d.match(/generated:\s*"([^"]*)"/);
console.log("data.js generated:", g ? g[1] : "(not found)");
