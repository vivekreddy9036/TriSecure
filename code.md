<<<<<<< HEAD
=======
(.venv) vivek@raspberrypi4:~/TriSecure $ python main.py
2026-02-25 21:01:44,661 - root - INFO - Logging initialized - Mode: development, Level: INFO
2026-02-25 21:01:44,661 - __main__ - INFO - ╔═══════════════════════════════════════════════════════════════════╗
2026-02-25 21:01:44,661 - __main__ - INFO - ║           TRISECURE - SECURE eVOTING SYSTEM v1.0                 ║
2026-02-25 21:01:44,661 - __main__ - INFO - ║      Raspberry Pi 4 + Ubuntu ARM + Face Recognition + NFC         ║
2026-02-25 21:01:44,662 - __main__ - INFO - ╚═══════════════════════════════════════════════════════════════════╝
2026-02-25 21:01:44,663 - repositories.voter_repository - INFO - SQLiteVoterRepository initialized: trisecure.db
2026-02-25 21:01:44,665 - repositories.vote_repository - INFO - SQLiteVoteRepository initialized: trisecure.db
2026-02-25 21:01:44,666 - repositories.audit_repository - INFO - SQLiteAuditRepository initialized: trisecure.db
2026-02-25 21:01:44,667 - core.audit_logger - INFO - AuditLogger initialized
2026-02-25 21:01:44,667 - core.session_manager - INFO - SessionManager initialized with 60s duration
2026-02-25 21:01:44,667 - security.blockchain_logger - INFO - BlockchainLogger initialized (internal hash chaining mode)
2026-02-25 21:01:44,667 - security.encryption_hooks - WARNING - Encryption disabled - running in plaintext mode
2026-02-25 21:01:44,667 - __main__ - INFO - TRIsecure system initialized
2026-02-25 21:01:44,667 - __main__ - INFO - ======================================================================
2026-02-25 21:01:44,668 - __main__ - INFO - TRISECURE INITIALIZATION
2026-02-25 21:01:44,668 - __main__ - INFO - Mode: development
2026-02-25 21:01:44,668 - __main__ - INFO - Database: trisecure.db
2026-02-25 21:01:44,668 - __main__ - INFO - ======================================================================
2026-02-25 21:01:44,668 - __main__ - INFO - Initializing NFC service...
2026-02-25 21:01:44,668 - services.nfc_service - INFO - NFCService (SPI) initialized (CS=D8, RESET=D25, baudrate=1000000)
2026-02-25 21:01:45,008 - services.nfc_service - INFO - Found PN532 with firmware version: 1.6
2026-02-25 21:01:45,023 - services.nfc_service - INFO - NFC device (SPI) initialized successfully
2026-02-25 21:01:45,024 - __main__ - INFO -   NFC: ✓ Ready
2026-02-25 21:01:45,024 - __main__ - INFO - Initializing camera service...
2026-02-25 21:01:45,024 - services.camera_service - INFO - CameraService initialized (device=/dev/video0, 640x480@30fps)
2026-02-25 21:01:45,801 - services.camera_service - INFO - Camera initialized: 640x480@30fps
2026-02-25 21:01:45,801 - __main__ - INFO -   Camera: ✓ Ready
2026-02-25 21:01:45,801 - __main__ - INFO - Initializing face recognition service...
2026-02-25 21:01:45,801 - services.face_service - INFO - FaceService initialized (model=hog, jitter=1)
2026-02-25 21:01:45,802 - services.face_service - WARNING - face_recognition library not installed. Running in simulation mode.
2026-02-25 21:01:45,802 - __main__ - INFO -   Face: ⚠ Simulation mode
2026-02-25 21:01:45,802 - core.auth_pipeline - INFO - AuthenticationPipeline initialized with face threshold=0.7
2026-02-25 21:01:45,803 - core.audit_logger - INFO - [AUDIT] CONFIG_LOADED - System initialized in development mode
2026-02-25 21:01:45,826 - __main__ - INFO - ✓ TRIsecure initialization complete
2026-02-25 21:01:45,827 - __main__ - INFO - 
Developer Mode: Running example workflow...
2026-02-25 21:01:45,827 - __main__ - INFO - Starting voter registration: John Doe
2026-02-25 21:01:45,827 - __main__ - INFO -   → Present NFC card
2026-02-25 21:01:45,827 - services.nfc_service - INFO - Waiting for NFC card...
2026-02-25 21:01:46,491 - services.nfc_service - INFO - NFC card read successfully: C6CA2407
2026-02-25 21:01:46,491 - core.audit_logger - INFO - [AUDIT] VOTER_NFC_REGISTERED - NFC registered for John Doe
2026-02-25 21:01:46,507 - __main__ - INFO -   → Capturing face image
2026-02-25 21:01:46,541 - core.audit_logger - INFO - [AUDIT] VOTER_FACE_REGISTERED - Face embedding captured for John Doe
2026-02-25 21:01:46,571 - repositories.voter_repository - INFO - Voter saved: 1d687d39-485e-428f-aa77-eccc2d77abea
2026-02-25 21:01:46,571 - core.audit_logger - INFO - [AUDIT] VOTER_REGISTERED - Voter registered: John Doe
2026-02-25 21:01:46,591 - __main__ - INFO - ✓ Voter registered: 1d687d39-485e-428f-aa77-eccc2d77abea
2026-02-25 21:01:46,592 - __main__ - INFO - Voter registered: 1d687d39-485e-428f-aa77-eccc2d77abea
2026-02-25 21:01:46,592 - __main__ - INFO - Starting voting workflow for candidate: Candidate A
2026-02-25 21:01:46,626 - services.nfc_service - INFO - NFC card read successfully: C6CA2407
2026-02-25 21:01:46,626 - __main__ - INFO -   → NFC card read: C6CA2407
2026-02-25 21:01:46,631 - core.auth_pipeline - INFO - Starting authentication pipeline for NFC UID: C6CA2407
2026-02-25 21:01:46,632 - core.audit_logger - INFO - [AUDIT] NFC_READ_SUCCESS - NFC card read successfully: C6CA2407
2026-02-25 21:01:46,652 - core.auth_pipeline - INFO - Voter found: 1d687d39-485e-428f-aa77-eccc2d77abea
2026-02-25 21:01:46,652 - core.audit_logger - INFO - [AUDIT] VOTER_VERIFIED - Voter verified successfully
2026-02-25 21:01:46,670 - core.audit_logger - WARNING - [AUDIT] FACE_MATCH_FAILED - Face match failed: Face confidence 0.00 below threshold 0.7
2026-02-25 21:01:46,688 - __main__ - ERROR - Authentication failed: Face verification failed
2026-02-25 21:01:46,689 - __main__ - INFO - Vote cast: ✗ Failed
2026-02-25 21:01:46,689 - __main__ - INFO - ======================================================================
2026-02-25 21:01:46,689 - __main__ - INFO - TRISECURE STATISTICS
2026-02-25 21:01:46,690 - __main__ - INFO - ======================================================================
2026-02-25 21:01:46,691 - __main__ - INFO - Registered Voters: 1
2026-02-25 21:01:46,691 - __main__ - INFO - Voted: 0
2026-02-25 21:01:46,692 - __main__ - INFO - Eligible: 1
2026-02-25 21:01:46,697 - repositories.vote_repository - INFO - Vote chain empty - integrity verified
2026-02-25 21:01:46,698 - security.blockchain_logger - INFO - Blockchain integrity check: VALID
2026-02-25 21:01:46,698 - __main__ - INFO - 
Votes Cast: 0
2026-02-25 21:01:46,698 - __main__ - INFO - Blockchain Valid: ✓ Yes
2026-02-25 21:01:46,701 - __main__ - INFO - 
Recent Audit Events: 10
2026-02-25 21:01:46,702 - __main__ - INFO -   [FACE_MATCH_FAILED] Face match failed: Face confidence 0.00 below threshold 0.7
2026-02-25 21:01:46,702 - __main__ - INFO -   [VOTER_VERIFIED] Voter verified successfully
2026-02-25 21:01:46,702 - __main__ - INFO -   [NFC_READ_SUCCESS] NFC card read successfully: C6CA2407
2026-02-25 21:01:46,702 - __main__ - INFO - ======================================================================
2026-02-25 21:01:46,704 - repositories.vote_repository - INFO - Vote chain empty - integrity verified
2026-02-25 21:01:46,704 - security.blockchain_logger - INFO - Blockchain integrity check: VALID
2026-02-25 21:01:46,704 - __main__ - INFO - Vote Integrity: ✓ VALID
2026-02-25 21:01:46,705 - __main__ - INFO - Shutting down TRIsecure...
2026-02-25 21:01:46,705 - services.nfc_service - INFO - NFC device closed
ioctl(VIDIOC_QBUF): Bad file descriptor
2026-02-25 21:01:46,711 - services.camera_service - INFO - Camera closed
2026-02-25 21:01:46,711 - core.audit_logger - INFO - [AUDIT] CONFIG_LOADED - System shutdown complete
2026-02-25 21:01:46,730 - __main__ - INFO - ✓ TRIsecure shutdown complete
>>>>>>> d10afb66f539bd2daf1ef19d0b4c554f0718ceed
