const express = require('express');
const morgan = require('morgan');
const path = require('path');
const fs = require('fs');
const cookieParser = require('cookie-parser');
const bodyParser = require('body-parser');
const mysql = require('mysql'); 
require("dotenv").config({ path: ".env" });

const app = express();

app.set('port', process.env.PORT || 8000);

// EJS 설정
app.set('views', [path.join(__dirname, 'views')]) //path.join(__dirname, '../node2/views')]);  // 두 개의 뷰 경로 설정
app.set('view engine', 'ejs');

app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());

// 정적 파일 제공 설정
app.use(express.static(path.join(__dirname, 'public')));

// MySQL 설정
const artdb_config = {
    host: process.env.DB_HOST,  // MySQL 도커 컨테이너의 호스트 이름 또는 IP 주소
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME_ART
};

// 기본 경로 설정
app.get('/', function(req, res) {
    res.render('index');
});

// '/index' 경로도 설정
app.get('/index', function(req, res) {
    res.render('index');
});

// detail 페이지 경로 설정
app.get('/detail', function(req, res) {
    const artId = req.query.art_id;

    const connection = mysql.createConnection(artdb_config);
    connection.connect();

    connection.query('SELECT * FROM art_info WHERE art_id = ?', [artId], function (error, results, fields) {
        if (error) throw error;

        const artwork = results[0];
        connection.query('SELECT * FROM art_info', function (error, results, fields) {
            if (error) throw error;

            const artworks = results;
            res.render('detail', { artwork: artwork, artworks: artworks });
        });
    });

    connection.end();
});

const main = require('./routes/main.js');
app.use('/', main);

app.listen(app.get('port'), () => {
    const dir = './saveUserImg';
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);
    console.log(`${app.get('port')} Port: Server Started~!!`);
});
