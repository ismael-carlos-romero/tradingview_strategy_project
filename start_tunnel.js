const localtunnel = require('localtunnel');
const fs = require('fs');
const path = require('path');

const logFile = path.join(__dirname, 'localtunnel_url.txt');

console.log("Starting localtunnel on port 8055...");
localtunnel({ port: 8055 })
  .then(tunnel => {
    console.log("Tunnel established at:", tunnel.url);
    fs.writeFileSync(logFile, tunnel.url, 'utf-8');
    
    tunnel.on('close', () => {
      console.log("Tunnel closed.");
      fs.writeFileSync(logFile, "Error: Tunnel closed", 'utf-8');
    });
  })
  .catch(err => {
    console.error("Tunnel error:", err);
    fs.writeFileSync(logFile, "Error: " + err.message, 'utf-8');
  });
