const express = require('express');
const router = express.Router();
const bodyParser = require('body-parser');
const multer = require('multer');
const AWS = require('aws-sdk');
const axios = require('axios');
require("dotenv").config({ path: "../.env" });
const FormData = require('form-data');

router.use(bodyParser.json());
router.use(bodyParser.urlencoded({ extended: false }));
router.use(express.json());
router.use(express.urlencoded({ extended: true }));

const ID = process.env.AWS_ACCESS_KEY_ID;
const SECRET = process.env.AWS_SECRET_ACCESS_KEY;
const BUCKET_NAME = process.env.AWS_S3_BUCKET_NAME;
const MYREGION = process.env.AWS_REGION;
const MY_HOST = process.env.MY_HOST;

AWS.config.update({
    accessKeyId: ID,
    secretAccessKey: SECRET,
    region: MYREGION
});

const s3 = new AWS.S3();

const storage = multer.memoryStorage();
const upload = multer({ storage: storage });

router.post('/upload', upload.single('file'), async (req, res) => {
    const file = req.file;

    if (!file) {
        console.error('No file received.');
        return res.status(400).json({ success: false, error: 'No file received.' });
    }

    const originalName = file.originalname;
    const encodedName = encodeURIComponent(originalName);
    const params = {
        Bucket: BUCKET_NAME,
        Key: `uploadUserImg/${encodedName}`,  // URL-safe 파일명 사용
        Body: file.buffer,
        ContentType: file.mimetype
    };

    s3.upload(params, async (err, data) => {
        if (err) {
            console.error('Error uploading file:', err);
            return res.status(500).json({ success: false, error: err });
        }

        console.log('File uploaded successfully:', data);

        try {
            const saveResponse = await axios.post(`${MY_HOST}/saveUserImg`, {
                user_img_url: data.Location
            });

            if (saveResponse.data.success) {
                const formData = new FormData();
                formData.append('file', file.buffer, {
                    filename: originalName,
                    contentType: file.mimetype
                });

                const similarityResponse = await axios.post(`${MY_HOST}/findSimilarArt`, formData, {
                    headers: {
                        ...formData.getHeaders()
                    }
                });

                res.status(200).json({ success: true, imgUrl: data.Location, similarArt: similarityResponse.data });
            } else {
                res.status(500).json({ success: false, error: 'Failed to save image URL to database' });
            }
        } catch (error) {
            console.error('Error finding similar art:', error);
            res.status(500).json({ success: false, error: 'Failed to find similar art' });
        }
    });
});

router.post('/confirmArt', async (req, res) => {
    const { art_id } = req.body;

    try {
        const response = await axios.post(`${MY_HOST}/postArtInfo`, { art_id });
        if (response.data.success) {
            res.status(200).json({ success: true });
        } else {
            res.status(500).json({ success: false, error: 'Failed to confirm art' });
        }
    } catch (error) {
        console.error('Error confirming art:', error);
        res.status(500).json({ success: false, error: 'Failed to confirm art' });
    }
});

router.post('/retrySimilarArt', upload.single('file'), async (req, res) => {
    const file = req.file;

    if (!file) {
        console.error('No file received.');
        return res.status(400).json({ success: false, error: 'No file received.' });
    }

    const originalName = file.originalname;
    const formData = new FormData();
    formData.append('file', file.buffer, {
        filename: originalName,
        contentType: file.mimetype
    });

    try {
        const similarityResponse = await axios.post(`${MY_HOST}/findSimilarArt`, formData, {
            headers: {
                ...formData.getHeaders()
            }
        });

        res.status(200).json({ success: true, similarArt: similarityResponse.data });
    } catch (error) {
        console.error('Error finding similar art:', error);
        res.status(500).json({ success: false, error: 'Failed to find similar art' });
    }
});

module.exports = router;
