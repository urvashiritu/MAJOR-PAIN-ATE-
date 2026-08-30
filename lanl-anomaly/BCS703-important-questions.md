# BCS703 - Cryptography and Network Security
## Important Questions

---

## Module 1: Model Network Security, Classical Encryption Technique, Block Ciphers and Data Encryption Standards

1. Explain the Model for Network Security with a neat diagram. Describe the roles of sender, receiver, opponent, security transformation, secret information, and trusted third party.

2. Explain the Symmetric Cipher Model with a neat diagram. List and explain the five elements of a symmetric encryption scheme and the requirements for secure symmetric encryption.

3. Explain substitution ciphers and describe the Caesar Cipher.
   **Numerical:** Encrypt the plaintext "MEET ME AFTER THE TOGA PARTY" using Caesar Cipher with shift k = 3. Show how brute-force attack is applied on Caesar cipher.

4. Explain Monoalphabetic Cipher. Discuss why it is vulnerable to frequency analysis, diagram, and trigram analysis with a suitable illustration.

5. Explain the Playfair Cipher with a neat diagram. Describe the encryption rules used in Playfair cipher.
   **Numerical:** Construct the Playfair matrix using the keyword "MONARCHY" and encrypt the plaintext "INSTRUMENT".

6. Explain the Hill Cipher and its mathematical basis.
   **Numerical:** Encrypt the plaintext "PAYMOREMONEY" using a 3×3 Hill cipher key matrix, showing all matrix operations modulo 26. Explain why Hill cipher is vulnerable to known-plaintext attack.

7. Explain Polyalphabetic Ciphers and describe the Vigenère Cipher with encryption and decryption equations.
   **Numerical:** Encrypt the message "WEAREDISCOVEREDSAVEYOURSELF" using the keyword "DECEPTIVE".

8. Explain the One-Time Pad. Prove that it provides perfect secrecy and discuss its practical limitations.

9. Explain Steganography. Differentiate between cryptography and steganography with suitable examples.

10. Explain Traditional Block Cipher Structures. Describe the Data Encryption Standard (DES) with a neat diagram, explain a DES round, discuss the strength of DES, and list block cipher design principles.

---

## Module 2: Pseudorandom Number Generators, Public Key Cryptography and RSA, Diffie-Hellman Key Exchange

1. Explain Pseudorandom Number Generators (PRNG). Describe the requirements of a good PRNG and explain why PRNGs are important in cryptography.

2. Explain the Linear Congruential Generator (LCG) method with parameters m, a, c, X₀. Discuss period, randomness, and weaknesses of LCG.
   **Numerical:** Given a = 7, c = 0, m = 32, X₀ = 1, generate the first five pseudorandom numbers and determine the period of the sequence.

3. Explain the working of the Blum Blum Shub generator and justify why it is considered a cryptographically secure PRNG.
   **Numerical:** Given p = 383, q = 503, seed s = 101355, generate the first few output bits using the BBS algorithm.

4. Explain the principles of public-key cryptosystems. With neat diagrams, explain encryption and decryption using public and private keys.

5. Explain how public-key cryptography is used for confidentiality, authentication, digital signatures, and key exchange.

6. List and explain the essential requirements that a public-key algorithm must satisfy.

7. Discuss different attacks possible on public-key cryptosystems and explain why public-key encryption is not used for bulk data encryption.

8. Explain the RSA algorithm in detail, including key generation, encryption, decryption, computational aspects, and security of RSA.
   **Numerical:** Given p = 17, q = 11, e = 7, compute n, φ(n), and private key d. Encrypt the message M = 88. Decrypt the ciphertext to recover the original message.

9. Explain the Diffie-Hellman algorithm with steps and illustrate the Man-in-the-Middle attack.

10. Explain Elliptic Curve Cryptography (ECC) with reference to elliptic curve key exchange, elliptic curve encryption/decryption, and security advantages of ECC over RSA.

---

## Module 3: Applications of Cryptographic Hash Functions, Two Simple Hash Functions, Key Management and Distribution

1. Explain the applications of cryptographic hash functions with neat diagrams for message authentication, digital signatures, and integrity verification.

2. Explain two simple hash functions (XOR and rotated XOR) and discuss why they are insecure for cryptographic applications.

3. Define preimage resistance, second preimage resistance, and collision resistance. Explain the security requirements of cryptographic hash functions.

4. Explain symmetric key distribution using symmetric encryption. Describe the role of KDC, master keys, and session keys with a neat diagram.

5. Explain the key hierarchy concept and discuss session key lifetime and hierarchical key control.

6. Describe the key distribution scenario using a Key Distribution Center (KDC). Explain each step using nonces and authentication messages.

7. Explain symmetric key distribution using asymmetric encryption. Discuss the Merkle scheme and explain the man-in-the-middle attack with a diagram.

8. Explain distribution of public keys using public announcement, public directory, and public-key authority. Compare their security weaknesses.

9. Explain public-key certificates and X.509 certificates. Describe the certificate structure, fields, and certificate lifecycle with a neat diagram.

10. Explain Public Key Infrastructure (PKI). Describe the components of PKI such as Certification Authority (CA), Registration Authority (RA), Certificate repository, and End entities. Explain how PKI supports secure key management and trust establishment.

---

## Module 4: User Authentication, Web Security

1. Explain remote user authentication principles. Differentiate between identification and verification and explain the means of authentication.

2. Explain the NIST model for electronic user authentication with a neat diagram. Describe the roles of RA, CSP, claimant, verifier, and relying party.

3. Explain mutual authentication. Discuss replay attacks and explain the use of timestamps and challenge-response techniques to prevent them.

4. Explain remote user authentication using symmetric encryption. Describe the KDC-based authentication protocol with message exchanges.

5. Explain Kerberos authentication system. Describe the motivation, requirements, and architecture of Kerberos.

6. Explain the Kerberos Version 4 authentication protocol with neat message flow diagrams. Discuss the roles of AS, TGS, tickets, and authenticators.

7. Explain Kerberos realms and inter-realm authentication. Describe how Kerberos supports authentication across multiple realms.

8. Explain remote user authentication using asymmetric encryption. Compare it with symmetric-key based authentication.

9. Explain Web security considerations and discuss the major Web security threats.

10. Explain Transport Layer Security (TLS) architecture. Describe the TLS Record Protocol and Handshake Protocol with neat diagrams.

11. Explain Transport Layer Security (TLS) architecture. Describe the TLS Record Protocol and Handshake Protocol with neat diagrams.

12. Explain S/MIME architecture and services. Describe Pretty Good Privacy (PGP) and compare S/MIME and PGP.

---

## Module 5: DomainKeys, IP Security

1. Explain DomainKeys Identified Mail (DKIM) and state its objectives.

2. Describe the architecture and operation of DKIM with a neat diagram.

3. Explain the DKIM message signing and verification process, highlighting the role of DNS.

4. Discuss the email threats addressed by DKIM.

5. Explain IP Security (IPsec) and describe the security services provided by IPsec.

6. Explain the IPsec architecture, including Security Association (SA), Security Policy Database (SPD), and Security Association Database (SAD).

7. Explain Encapsulating Security Payload (ESP) and describe its packet format with a neat diagram.

8. Differentiate between transport mode and tunnel mode of ESP.

9. Explain the anti-replay mechanism in IPsec.

10. Explain the combining of security associations in IPsec.

11. Explain the Internet Key Exchange (IKE) protocol and its role in IPsec key management.

12. Write short notes on IPsec security policy and traffic processing.
