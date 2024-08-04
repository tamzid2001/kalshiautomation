# AWS EC2 and Python Tutorial

## Introduction

This tutorial demonstrates how to set up an AWS EC2 instance, run Python scripts continuously using nohup, and manage processes effectively. Learn essential commands for a smooth development experience on EC2.

## Tutorial Contents

### 1. Setting up an EC2 Instance

# AWS EC2 and Python Tutorial

## Introduction

This tutorial demonstrates how to set up an AWS EC2 instance, run Python scripts continuously using nohup, and manage processes effectively. Learn essential commands for a smooth development experience on EC2.

## Tutorial Contents

### 1. Setting up an EC2 Instance

Follow these steps to set up your AWS EC2 instance:

a. **Create an AWS Account**
   - Go to [AWS Console](https://aws.amazon.com/)
   - Click "Create an AWS Account" and follow the prompts

b. **Launch an EC2 Instance**
   - Log in to the AWS Management Console
   - Navigate to EC2 under "Compute" services
   - Click "Launch Instance"
   - Choose an Amazon Machine Image (AMI) - e.g., Amazon Linux 2 or Ubuntu
   - Select an instance type (t2.micro is eligible for free tier)
   - Configure instance details (use default settings for basic setup)
   - Add storage (default is usually sufficient for beginners)
   - Add tags (optional)
   - Configure security group:
     - Allow SSH traffic (port 22) from your IP address
     - Allow HTTP traffic (port 80) if you plan to host a web application
   - Review and launch
   - Create a new key pair, download it, and keep it secure

c. **Connect to Your EC2 Instance**
   - Wait for the instance to initialize (check the "Instance State")
   - Select your instance and click "Connect"
   - Follow the instructions to SSH into your instance:
     ```
     chmod 400 your-key-pair.pem
     ssh -i "your-key-pair.pem" ec2-user@your-instance-public-dns
     ```

d. **Update and Install Python (if not pre-installed)**
   ```bash
   sudo yum update -y
   sudo yum install python3 -y
   ```

e. **Verify Python Installation**
   ```bash
   python3 --version
   ```

Now your EC2 instance is set up and ready for the next steps in the tutorial.

### 2. Running Python Scripts Continuously

Use the following command to run your Python script in the background:

```bash
nohup python3 my_script.py &
```

### 3. Essential Commands

Master these commands for effective EC2 and process management:

- Get root access:
  ```bash
  sudo su
  ```

- List Python processes:
  ```bash
  ps aux | grep python3
  ```

- Terminate a specific process:
  ```bash
  kill 2322
  ```
  Replace `2322` with the actual process ID you want to terminate.

- View your script's recent activity:
  ```bash
  tail -f nohup.out
  ```

## Tips for Process Management

- Always use `nohup` when you want a script to continue running after you've logged out of the EC2 instance.
- Regularly check running processes to ensure optimal resource utilization.
- Use `kill` command judiciously to terminate processes that are no longer needed.

## Conclusion

By mastering these commands and techniques, you'll be able to efficiently manage Python scripts on your AWS EC2 instance, ensuring continuous operation and effective process control.

Happy coding!
```markdown
# Kalshi Market Analysis Automation

This repository contains a Python-based automation tool for analyzing and monitoring Kalshi market data. The tool fetches active market data, identifies popular markets based on trading volume, calculates Simple Moving Averages (SMA), and provides actionable alerts based on detected patterns.

## Features

- Fetches and processes active markets from Kalshi API.
- Identifies popular markets with high trading volumes.
- Calculates the 9-period Simple Moving Average (SMA9) to detect market patterns.
- Generates alerts for potential trading decisions based on SMA patterns.
- Monitors market prices in real-time.

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/tamzid2001/kalshi-market-analysis.git
    cd kalshi-market-analysis
    ```

2. Create a virtual environment and activate it:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Configure your Kalshi API credentials in the `config` section of the code:
    ```python
    config = kalshi_python.Configuration()
    kalshi_api = kalshi_python.ApiInstance(
        email='your-email@example.com',
        password='your-password',
        configuration=config,
    )
    ```

## Usage

Run the main script to start the market analysis:
```bash
python kalshi.py
```

The script will:
- Fetch active markets from Kalshi API.
- Identify popular markets based on a predefined volume threshold.
- Monitor market prices, calculate SMA9, and detect patterns.
- Generate actionable alerts for potential trading decisions.

## Example

The following example demonstrates how the tool works:
```python
if __name__ == "__main__":
    main()
```

## Screenshots

Here are some screenshots of the tool in action:

![Screenshot 1](path/to/Screenshot1.png)
![Screenshot 2](path/to/Screenshot2.png)
![Screenshot 3](path/to/Screenshot3.png)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For any questions or inquiries, please contact Tamzid Ullah at tamzid257@gmail.com.

---

🚀 Happy Trading!

Paypal: https://paypal.me/tamzidullah
