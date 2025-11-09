let html5QrCode;
let currentTeamId = null;
let currentMembers = [];

// ✅ Start the QR Scanner
async function startScanner() {
  const mascot = document.getElementById("mascot-loader");
  mascot.style.display = "flex";

  const reader = document.getElementById("reader");
  reader.innerHTML = ""; // clear old camera preview

  // Create new scanner
  html5QrCode = new Html5Qrcode("reader");

  const qrConfig = { fps: 10, qrbox: 250 };

  try {
    await html5QrCode.start(
      { facingMode: "environment" },
      qrConfig,
      async (decodedText) => {
        mascot.style.display = "none";

        try {
          const teamData = JSON.parse(decodedText);
          if (teamData.team_id) {
            currentTeamId = teamData.team_id;
            await html5QrCode.stop();
            showTeamDetails(teamData.team_id);
          } else {
            alert("⚠️ Invalid QR Code!");
          }
        } catch (err) {
          console.error("QR Parsing Error:", err);
          alert("⚠️ Could not read QR code properly.");
        }
      },
      () => {} // optional scanning callback
    );
  } catch (err) {
    console.error("Scanner start error:", err);
    alert("⚠️ Please allow camera access and try again.");
  } finally {
    setTimeout(() => (mascot.style.display = "none"), 1200);
  }
}

// ✅ Display team details
async function showTeamDetails(teamId) {
  const response = await fetch(`/team/${teamId}`);
  const data = await response.json();

  if (data.error) {
    alert("⚠️ Team not found!");
    return;
  }

  const team = data.team;
  currentMembers = data.members;

  document.getElementById("team-info").classList.remove("hidden");
  document.getElementById("team-name").innerText = `Team: ${team.team_name}`;
  document.getElementById("team-members").innerText = "Members:";

  const tbody = document.querySelector("#members-table tbody");
  tbody.innerHTML = "";

  currentMembers.forEach((member) => {
    const row = document.createElement("tr");
    row.dataset.memberId = member.member_id;
    row.innerHTML = `
      <td>${member.member_name}</td>
      <td><input type="checkbox" ${member.check_in ? "checked" : ""}></td>
      <td><input type="checkbox" ${member.snacks ? "checked" : ""}></td>
      <td><input type="checkbox" ${member.dinner ? "checked" : ""}></td>
      <td><input type="checkbox" ${member.check_out ? "checked" : ""}></td>
    `;
    tbody.appendChild(row);
  });

  document.getElementById("scan-next").classList.remove("hidden");
}

// ✅ Update members in database
async function updateMembers() {
  if (!currentTeamId || currentMembers.length === 0) {
    alert("⚠️ No team data found!");
    return;
  }

  const rows = document.querySelectorAll("#members-table tbody tr");
  const updatedMembers = [];

  rows.forEach((row) => {
    const checkboxes = row.querySelectorAll("input[type='checkbox']");
    updatedMembers.push({
      member_id: row.dataset.memberId,
      check_in: checkboxes[0].checked ? 1 : 0,
      snacks: checkboxes[1].checked ? 1 : 0,
      dinner: checkboxes[2].checked ? 1 : 0,
      check_out: checkboxes[3].checked ? 1 : 0,
    });
  });

  const response = await fetch("/update_members", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ members: updatedMembers }),
  });

  const result = await response.json();
  if (result.status === "updated") {
    alert("✅ Status updated successfully!");
  } else {
    alert("⚠️ Update failed. Try again.");
  }
}

// ✅ Restart scanner for next QR
async function startNextScan() {
  const mascot = document.getElementById("mascot-loader");
  mascot.style.display = "flex";

  // Hide old data
  document.getElementById("team-info").classList.add("hidden");
  document.getElementById("scan-next").classList.add("hidden");

  try {
    if (html5QrCode) {
      await html5QrCode.stop();
      await html5QrCode.clear();
    }
  } catch (err) {
    console.warn("Error stopping scanner:", err);
  }

  // Short delay before restarting
  setTimeout(() => {
    startScanner();
  }, 1000);
}

// Start scanner on load
window.onload = () => {
  startScanner();
};
