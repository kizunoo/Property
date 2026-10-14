const localtunnel = require("localtunnel");
const fs = require("fs");

(async () => {
  try {
    const tunnel = await localtunnel({ port: 3000 });
    const url = tunnel.url;
    console.log("TUNNEL_PUBLIC_URL=" + url);
    fs.writeFileSync("tunnel_url.txt", url, "utf-8");

    tunnel.on("close", () => {
      console.log("Tunnel closed");
    });
    tunnel.on("error", (err) => {
      console.error("Tunnel error:", err);
    });
  } catch (err) {
    console.error("Failed to create tunnel:", err);
  }
})();
