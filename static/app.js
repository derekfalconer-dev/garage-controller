"use strict";

const POLL_INTERVAL_MS = 1000;
const EVENT_POLL_INTERVAL_MS = 3000;

const elements = {
    connectionIndicator: document.getElementById("connectionIndicator"),
    hostname: document.getElementById("hostname"),
    statusCard: document.getElementById("statusCard"),
    statusIcon: document.getElementById("statusIcon"),
    doorState: document.getElementById("doorState"),
    stateDuration: document.getElementById("stateDuration"),
    lastTransition: document.getElementById("lastTransition"),
    lastCommand: document.getElementById("lastCommand"),
    monitorState: document.getElementById("monitorState"),
    cooldownState: document.getElementById("cooldownState"),
    smsState: document.getElementById("smsState"),
    alertState: document.getElementById("alertState"),
    toggleButton: document.getElementById("toggleButton"),
    testNotificationButton: document.getElementById("testNotificationButton"),
    message: document.getElementById("message"),
    eventList: document.getElementById("eventList"),
};

let requestInProgress = false;
let notificationTestInProgress = false;

function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds));

    if (seconds < 60) {
        return `${seconds} second${seconds === 1 ? "" : "s"}`;
    }

    const minutes = Math.floor(seconds / 60);

    if (minutes < 60) {
        return `${minutes} minute${minutes === 1 ? "" : "s"}`;
    }

    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;

    if (remainingMinutes === 0) {
        return `${hours} hour${hours === 1 ? "" : "s"}`;
    }

    return `${hours}h ${remainingMinutes}m`;
}

function formatTimestamp(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString();
}

function setConnectionState(online) {
    elements.connectionIndicator.textContent = online
        ? "Connected"
        : "Disconnected";

    elements.connectionIndicator.className = online
        ? "connection-indicator connection-online"
        : "connection-indicator connection-offline";
}

function showMessage(text, isError = false) {
    elements.message.textContent = text;
    elements.message.className = isError
        ? "message message-error"
        : "message message-success";
}

function renderStatus(status) {
    const isOpen = status.door_state === "OPEN";
    const isClosed = status.door_state === "CLOSED";

    elements.hostname.textContent = status.hostname;
    elements.statusCard.className = "status-card";

    if (isOpen) {
        elements.statusCard.classList.add("status-open");
        elements.statusIcon.textContent = "!";
    } else if (isClosed) {
        elements.statusCard.classList.add("status-closed");
        elements.statusIcon.textContent = "✓";
    } else {
        elements.statusCard.classList.add("status-unknown");
        elements.statusIcon.textContent = "?";
    }

    elements.doorState.textContent = status.door_state;
    elements.stateDuration.textContent =
        `In this state for ${formatDuration(
            status.seconds_in_current_state
        )}`;

    elements.lastTransition.textContent =
        formatTimestamp(status.last_transition_at);

    elements.lastCommand.textContent =
        formatTimestamp(status.last_command_at);

    elements.monitorState.textContent = status.monitor_running
        ? "Running"
        : "Stopped";

    elements.cooldownState.textContent =
        status.cooldown_remaining_seconds > 0
            ? `${status.cooldown_remaining_seconds.toFixed(1)} seconds`
            : "Ready";

    elements.smsState.textContent = status.sms_enabled
        ? "Enabled"
        : "Not configured";

    if (status.door_state !== "OPEN") {
        elements.alertState.textContent =
            `After ${formatDuration(status.open_alert_seconds)}`;
    } else if (status.open_alert_sent) {
        elements.alertState.textContent = "Alert processed";
    } else if (status.open_alert_due_in_seconds !== null) {
        elements.alertState.textContent =
            `Due in ${formatDuration(
                status.open_alert_due_in_seconds
            )}`;
    } else {
        elements.alertState.textContent = "Monitoring";
    }

    elements.toggleButton.disabled =
        requestInProgress || !status.command_allowed;

    if (requestInProgress) {
        elements.toggleButton.textContent = "Sending Command...";
    } else if (!status.command_allowed) {
        elements.toggleButton.textContent = "Please Wait";
    } else {
        elements.toggleButton.textContent = "Operate Garage Door";
    }
}

function renderEvents(events) {
    elements.eventList.replaceChildren();

    if (!events.length) {
        const empty = document.createElement("p");
        empty.className = "empty-events";
        empty.textContent = "No events recorded.";
        elements.eventList.appendChild(empty);
        return;
    }

    for (const event of events) {
        const row = document.createElement("div");
        row.className = "event-row";

        const content = document.createElement("div");

        const message = document.createElement("strong");
        message.textContent = event.message;

        const type = document.createElement("span");
        type.className = "event-type";
        type.textContent = event.event_type.replaceAll("_", " ");

        const timestamp = document.createElement("time");
        timestamp.textContent = formatTimestamp(event.timestamp);

        content.append(message, type);
        row.append(content, timestamp);
        elements.eventList.appendChild(row);
    }
}

async function refreshStatus() {
    try {
        const response = await fetch("/api/status", {
            cache: "no-store",
        });

        if (!response.ok) {
            throw new Error(`Status request failed: ${response.status}`);
        }

        const payload = await response.json();
        setConnectionState(true);
        renderStatus(payload.status);
    } catch (error) {
        console.error(error);
        setConnectionState(false);
        elements.toggleButton.disabled = true;
    }
}

async function refreshEvents() {
    try {
        const response = await fetch("/api/events", {
            cache: "no-store",
        });

        if (!response.ok) {
            throw new Error(`Event request failed: ${response.status}`);
        }

        const payload = await response.json();
        renderEvents(payload.events);
    } catch (error) {
        console.error(error);
    }
}


async function operateDoor() {
    const confirmed = window.confirm(
        "Operate the garage door?\n\n" +
        "The opener may open, stop, or close the door depending on its " +
        "current state."
    );

    if (!confirmed) {
        return;
    }

    requestInProgress = true;
    elements.toggleButton.disabled = true;
    elements.toggleButton.textContent = "Sending Command...";
    showMessage("");

    try {
        const response = await fetch("/api/toggle", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
        });

        const payload = await response.json();

        if (!response.ok || !payload.ok) {
            throw new Error(payload.message || "Command failed.");
        }

        showMessage(payload.message);
        renderStatus(payload.status);
        await refreshEvents();
    } catch (error) {
        console.error(error);
        showMessage(error.message || "Command failed.", true);
    } finally {
        requestInProgress = false;
        await refreshStatus();
    }
}

async function testNotifications() {
    if (notificationTestInProgress) {
        return;
    }

    notificationTestInProgress = true;
    elements.testNotificationButton.disabled = true;
    elements.testNotificationButton.textContent = "Sending...";
    showMessage("");

    try {
        const response = await fetch("/api/notifications/test", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
        });

        const payload = await response.json();

        if (!response.ok || !payload.ok) {
            throw new Error(
                payload.message || "Test notification failed."
            );
        }

        showMessage(payload.message);
        elements.testNotificationButton.textContent =
            "Notification Sent";

        await refreshEvents();
    } catch (error) {
        console.error(error);

        showMessage(
            error.message || "Test notification failed.",
            true
        );

        elements.testNotificationButton.textContent =
            "Notification Failed";
    } finally {
        window.setTimeout(() => {
            notificationTestInProgress = false;
            elements.testNotificationButton.disabled = false;
            elements.testNotificationButton.textContent =
                "Test Notifications";
        }, 2500);
    }
}

elements.toggleButton.addEventListener("click", operateDoor);

elements.testNotificationButton.addEventListener(
    "click",
    testNotifications
);

refreshStatus();
refreshEvents();

window.setInterval(refreshStatus, POLL_INTERVAL_MS);
window.setInterval(refreshEvents, EVENT_POLL_INTERVAL_MS);
