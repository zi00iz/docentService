// app.js
const express = require('express');
const morgan = require('morgan');
const path = require('path');
const fs = require('fs');
const cookieParser = require('cookie-parser');
const bodyParser = require('body-parser');
require("dotenv").config({ path: "../.env" });

const app = express();

app.set('port', process.env.PORT || 8000);

// EJS 설정 (views 폴더 대신 public 폴더 사용)
app.set('views', path.join(__dirname, 'public'));
app.set('view engine', 'ejs');

app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());

// 정적 파일 제공 설정
app.use(express.static(path.join(__dirname, 'public')));

// 기본 경로 설정
app.get('/', function(req, res) {
    res.render('index');
});

// '/index' 경로도 설정
app.get('/index', function(req, res) {
    res.render('index');
});

const main = require('./routes/main.js');
app.use('/', main);

app.listen(app.get('port'), () => {
    const dir = './uploadUserImg';
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);
    console.log(`${app.get('port')} Port: Server Started~!!`);
});
