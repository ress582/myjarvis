// Global variables for schedule management
let currentScheduleSuggestion = null;
let lastScheduleCheck = 0;
const SCHEDULE_CHECK_INTERVAL = 30000; // Check every 30 seconds

// Function to process AI response and detect scheduling information
function processAIResponse(response) {
    // Check if response contains scheduling information
    const scheduleRegex = /schedule\/(.*?)\/(.*?)\/(.*?)\/(.*)/;
    const match = response.match(scheduleRegex);
    
    if (match) {
        const [_, name, date, time, description] = match;
        showSchedulePopup(name, date, time, description);
    }
    
    // Display the response in the response div
    document.getElementById('response').innerHTML = response.replace(scheduleRegex, '');
}

// Function to show the schedule popup
function showSchedulePopup(name, date, time, description) {
    currentScheduleSuggestion = { name, date, time, description };
    
    // Update popup content
    document.getElementById('schedule-popup-name').textContent = name;
    document.getElementById('schedule-popup-date').textContent = date;
    document.getElementById('schedule-popup-time').textContent = time;
    document.getElementById('schedule-popup-description').textContent = description;
    
    // Show the popup
    document.getElementById('schedule-popup').style.display = 'flex';
}

// Function to show notification
function showNotification(title, body) {
    if (!('Notification' in window)) {
        console.log('This browser does not support desktop notification');
        return;
    }

    if (Notification.permission === 'granted') {
        new Notification(title, { body });
    } else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                new Notification(title, { body });
            }
        });
    }
}

// Function to check for new schedules
async function checkNewSchedules() {
    const currentTime = Date.now();
    if (currentTime - lastScheduleCheck < SCHEDULE_CHECK_INTERVAL) return;
    
    try {
        const response = await fetch('/get_schedule');
        const scheduleItems = await response.json();
        
        scheduleItems.forEach(item => {
            const scheduleDateTime = new Date(`${item.date}T${item.time}`);
            const timeDiff = scheduleDateTime.getTime() - currentTime;
            
            // Show notifications at different intervals
            if (timeDiff > 0) {
                // 15 minutes before
                if (timeDiff <= 900000 && timeDiff > 840000) { // 15 minutes = 900000ms
                    showNotification('Upcoming Event', `${item.name} in 15 minutes\n${item.description}`);
                }
                // 5 minutes before
                else if (timeDiff <= 300000 && timeDiff > 240000) { // 5 minutes = 300000ms
                    showNotification('Upcoming Event', `${item.name} in 5 minutes\n${item.description}`);
                }
                // 1 minute before
                else if (timeDiff <= 60000 && timeDiff > 55000) { // 1 minute = 60000ms
                    showNotification('Upcoming Event', `${item.name} in 1 minute\n${item.description}`);
                }
            }
            
            // Show popup at the exact scheduled time (within a 5-second window)
            if (timeDiff >= -5000 && timeDiff <= 5000) {
                showSchedulePopup(item.name, item.date, item.time, item.description);
            }
        });
        
        // Update schedule list
        updateScheduleList(scheduleItems);
        lastScheduleCheck = currentTime;
    } catch (error) {
        console.error('Error checking schedules:', error);
    }
}

// Function to update schedule list
function updateScheduleList(scheduleItems) {
    const scheduleList = document.getElementById('schedule-list');
    scheduleList.innerHTML = '';
    
    scheduleItems.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.className = 'schedule-item';
        itemElement.innerHTML = `
            <h4>${item.name}</h4>
            <p><strong>Date:</strong> ${item.date}</p>
            <p><strong>Time:</strong> ${item.time}</p>
            <p>${item.description}</p>
            <button class="delete-btn" onclick="deleteScheduleItem('${item.id}')">Delete</button>
        `;
        scheduleList.appendChild(itemElement);
    });
}

// Function to add the suggested schedule item
async function addScheduleSuggestion() {
    if (!currentScheduleSuggestion) return;
    
    try {
        const response = await fetch('/add_schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(currentScheduleSuggestion)
        });
        
        if (response.ok) {
            // Refresh the schedule list
            getScheduleItems();
            // Hide the popup
            dismissScheduleSuggestion();
        } else {
            console.error('Failed to add schedule item');
        }
    } catch (error) {
        console.error('Error adding schedule item:', error);
    }
}

// Function to dismiss the schedule suggestion popup
function dismissScheduleSuggestion() {
    document.getElementById('schedule-popup').style.display = 'none';
    currentScheduleSuggestion = null;
}

// Function to get and display schedule items
async function getScheduleItems() {
    try {
        const response = await fetch('/get_schedule');
        const scheduleItems = await response.json();
        
        const scheduleList = document.getElementById('schedule-list');
        scheduleList.innerHTML = '';
        
        scheduleItems.forEach(item => {
            const itemElement = document.createElement('div');
            itemElement.className = 'schedule-item';
            itemElement.innerHTML = `
                <h4>${item.name}</h4>
                <p><strong>Date:</strong> ${item.date}</p>
                <p><strong>Time:</strong> ${item.time}</p>
                <p>${item.description}</p>
                <button class="delete-btn" onclick="deleteScheduleItem('${item.id}')">Delete</button>
            `;
            scheduleList.appendChild(itemElement);
        });
    } catch (error) {
        console.error('Error fetching schedule items:', error);
    }
}

// Function to manually add a schedule item
async function addScheduleItem() {
    const title = document.getElementById('schedule-title').value;
    const date = document.getElementById('schedule-date').value;
    const time = document.getElementById('schedule-time').value;
    const description = document.getElementById('schedule-description').value;
    
    if (!title || !date || !time) {
        alert('Please fill in all required fields');
        return;
    }
    
    try {
        const response = await fetch('/add_schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: title,
                date,
                time,
                description
            })
        });
        
        if (response.ok) {
            // Clear form
            document.getElementById('schedule-title').value = '';
            document.getElementById('schedule-date').value = '';
            document.getElementById('schedule-time').value = '';
            document.getElementById('schedule-description').value = '';
            
            // Refresh schedule list
            getScheduleItems();
        } else {
            console.error('Failed to add schedule item');
        }
    } catch (error) {
        console.error('Error adding schedule item:', error);
    }
}

// Function to delete a schedule item
async function deleteScheduleItem(id) {
    if (!confirm('Are you sure you want to delete this schedule item?')) return;
    
    try {
        const response = await fetch(`/delete_schedule/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            getScheduleItems();
        } else {
            console.error('Failed to delete schedule item');
        }
    } catch (error) {
        console.error('Error deleting schedule item:', error);
    }
}

// Initialize schedule list and notification permission when page loads
document.addEventListener('DOMContentLoaded', () => {
    getScheduleItems();
    
    // Request notification permission
    if ('Notification' in window) {
        Notification.requestPermission();
    }
    
    // Start periodic schedule checking
    setInterval(checkNewSchedules, SCHEDULE_CHECK_INTERVAL);
});

// Function to check upcoming schedule items and send notifications
async function checkUpcomingSchedule() {
    const password = document.getElementById('password').value;
    if (!password) return;

    try {
        const response = await fetch(`/schedule?password=${encodeURIComponent(password)}`);
        const data = await response.json();
        
        if (data.items) {
            const now = new Date();
            data.items.forEach(item => {
                const eventTime = new Date(`${item.date}T${item.time}`);
                const timeDiff = eventTime - now;
                
                // Notify 15 minutes before the event
                if (timeDiff > 0 && timeDiff <= 15 * 60 * 1000) {
                    showNotification(
                        'Upcoming Event',
                        `${item.title} starts in ${Math.round(timeDiff / 60000)} minutes`
                    );
                }
            });
        }
    } catch (error) {
        console.error('Error checking upcoming schedule:', error);
    }
}

// Start periodic schedule checks
setInterval(checkUpcomingSchedule, 60000); // Check every minute

// Request notification permission when page loads
document.addEventListener('DOMContentLoaded', () => {
    if ('Notification' in window) {
        Notification.requestPermission();
    }
});
