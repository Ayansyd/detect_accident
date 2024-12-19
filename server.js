const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process'); // For executing shell commands

const app = express();
const PORT = process.env.PORT || 3000;

// Create an 'uploads' directory if it doesn't exist
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir);
}

// Helper function to format current date and time
function getCurrentTimestamp() {
    const now = new Date();
    const formattedDate = now.toISOString().split('T')[0]; // yyyy-mm-dd
    const formattedTime = now.toTimeString().split(' ')[0].replace(/:/g, '-'); // hh-mm-ss
    return `${formattedDate}_${formattedTime}`;
}

// Set up Multer storage configuration
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        cb(null, uploadsDir);
    },
    filename: function (req, file, cb) {
        const ext = path.extname(file.originalname);
        const baseName = path.basename(file.originalname, ext);
        const timestamp = getCurrentTimestamp(); // Generate timestamp in 'date_time' format
        cb(null, `${baseName}_${timestamp}${ext}`);
    }
});

// Configure multer for multiple files
const upload = multer({ 
    storage: storage,
    limits: { fileSize: 100 * 1024 * 1024 }, // Limit to 100MB per file
    fileFilter: (req, file, cb) => {
        const videoFileTypes = /avi|mp4|mkv/; // Acceptable video formats
        const logFileTypes = /txt|csv|json/; // Acceptable GPS log formats
        const extname = videoFileTypes.test(path.extname(file.originalname).toLowerCase()) ||
                        logFileTypes.test(path.extname(file.originalname).toLowerCase());
        
        if (extname) {
            return cb(null, true);
        } else {
            cb('Error: Only videos and GPS log files are allowed!');
        }
    }
});

// Define the upload route for multiple files
app.post('/upload', upload.array('files'), (req, res) => {
    if (req.files && req.files.length > 0) {
        const uploadedFiles = req.files.map(file => path.join(uploadsDir, file.filename));
        
        // Log the received files
        console.log(`Received files: ${uploadedFiles.join(', ')}`);

        // Transfer each uploaded file to the target IP address using SCP
        uploadedFiles.forEach(filePath => {
            const command = `scp ${filePath} iast@192.168.0.61:/home/iast/Desktop/`; // Adjust user and path as necessary
            exec(command, (error, stdout, stderr) => {
                if (error) {
                    console.error(`Error transferring file: ${error.message}`);
                    return;
                }
                if (stderr) {
                    console.error(`SCP stderr: ${stderr}`);
                    return;
                }
                console.log(`SCP stdout: ${stdout}`);
            });
        });

        res.json({ message: "Files uploaded successfully!", files: uploadedFiles });
    } else {
        console.log("No files received.");
        res.status(400).json({ message: "Failed to upload files" });
    }
});

// Endpoint to list uploaded files
app.get('/files', (req, res) => {
    fs.readdir(uploadsDir, (err, files) => {
        if (err) {
            return res.status(500).json({ message: "Unable to scan directory: " + err });
        }
        res.json(files);
    });
});

// Endpoint to serve specific files
app.get('/files/:filename', (req, res) => {
    const filePath = path.join(uploadsDir, req.params.filename);
    res.sendFile(filePath, (err) => {
        if (err) {
            res.status(err.status).end();
        }
    });
});

// Start the server
app.listen(PORT, () => {
    console.log(`Server is running on http://localhost:${PORT}`);
});
