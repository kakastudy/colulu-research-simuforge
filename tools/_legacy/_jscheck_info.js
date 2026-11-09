const fs = require("fs");
const path = "docs/rd_process_infographic.html";
const h = fs.readFileSync(path, "utf8");
const m = h.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log("no script block"); process.exit(1); }
try {
  new Function(m[1]);
  console.log("infographic JS syntax OK (" + m[1].length + " chars)");
} catch (e) {
  console.log("JS ERROR: " + e.message);
  process.exit(1);
}
console.log("v1.61 refs:", (h.match(/v1\.61/g) || []).length, "| v1.62 refs:", (h.match(/v1\.62/g) || []).length);
