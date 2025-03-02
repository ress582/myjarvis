// Global variables for schedule management
let currentScheduleSuggestion = null;

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

// Initialize schedule list when page loads
document.addEventListener('DOMContentLoaded', () => {
    getScheduleItems();
});