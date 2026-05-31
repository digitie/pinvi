const fs = require("fs");
const cp = require("child_process");
const files = cp.execSync("git ls-files", { encoding: "utf8" })
  .split(/\r?\n/).map(s => s.trim()).filter(f => f.endsWith(".md"));
const bad = [];
for (const f of files) {
  const t = fs.readFileSync(f, "utf8");
  const esc = (t.match(/\\[nt]/g) || []).length;
  const real = (t.match(/\n/g) || []).length;
  if (esc > 2 && real < esc) bad.push(`${f} esc=${esc} real=${real}`);
}
fs.writeFileSync("_verify.out", "CORRUPTED=" + bad.length + "\n" + bad.join("\n") + "\n");
