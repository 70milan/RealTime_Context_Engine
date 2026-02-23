const https = require('https');
const fs = require('fs');

const options = {
    hostname: 'api.github.com',
    path: '/repos/mjulez70/job_bandit/releases/latest',
    method: 'GET',
    headers: {
        'User-Agent': 'Test-App' // GitHub requires a user agent
    }
};

const req = https.request(options, res => {
    let data = '';
    res.on('data', d => data += d);
    res.on('end', () => {
        fs.writeFileSync('gh_response.json', JSON.stringify({
            statusCode: res.statusCode,
            data: data
        }));
    });
});

req.on('error', error => {
    fs.writeFileSync('gh_error.txt', error.toString());
});

req.end();
