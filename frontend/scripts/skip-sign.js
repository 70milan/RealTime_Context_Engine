// Used by build-local.bat when there is no signing certificate: does nothing, so the
// installer is built unsigned (electron-builder otherwise insists on signing when
// package.json points at a certificate file).
exports.default = async function skipSign() { };
