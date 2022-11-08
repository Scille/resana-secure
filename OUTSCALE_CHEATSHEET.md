# Outscale OOS configuration cheatsheet

## 1 Install AWS CLI


```sh
$ curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
$ unzip awscliv2.zip
```

## 2 Configure Outscale credentials in AWS CLI

Note you cannot use Outscale fancy EIM system configure access to OOS (i.e. Outscale's S3), you can only use
regular account.
You can get the access ID & secret Key from your personal account, then `Personal information & Access keys` -> `Access keys`.

Now to actually do the configuration:

```sh
$ ./awscliv2/dist/aws configure
AWS Access Key ID [None]: <access id>
AWS Secret Access Key [None]: <secret key>
Default region name [None]: cloudgouv-eu-west-1
Default output format [None]: json
```

This will create the files `~/.aws/config` and `~/.aws/credentials`, the latter containing your credential in clear text !

!!! Remember to remove the file `~/.aws/credentials` when you're done !!!

## 3 Using the AWS CLI

### 3.1 Overwiew

You must pass the `--endpoint https://oos.cloudgouv-eu-west-1.outscale.com/` when using the AWS CLI:

```sh
$ ./awscliv2/dist/aws s3 ls --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
```

See the [Outscale list of endpoints](https://docs.outscale.com/fr/userguide/R%C3%A9f%C3%A9rence-des-R%C3%A9gions-endpoints-et-Availability-Zones.html#_outscale_object_storage_oos).

### 3.2 Interesting commands

See [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-services-s3-commands.html#using-s3-commands-managing-buckets-creating)

```sh
# Create a bucket
$ aws s3 mb s3://turbo-flipiti-flop-1664 --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
# List buckets
$ aws s3 ls --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
# Copy file to bucket
$ aws s3 cp ./file1 s3://turbo-flipiti-flop-1664/file1 --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
# Remove file from bucket
$ aws s3 rm s3://turbo-flipiti-flop-1664/file1 --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
# Remove empty bucket
$ aws s3 rb s3://turbo-flipiti-flop-1664 --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
```

## 4 Configure access control to a bucket

See current access control:

```sh
$ aws s3api get-bucket-acl --bucket resana-secure-demo-blocks --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/
{
    "Owner": {
        "DisplayName": "137309343814",
        "ID": "bf27a534c828c92588adaf938a7396fb7ef9e027350cc4187a47d858c1f460d7"
    },
    "Grants": [
        {
            "Grantee": {
                "DisplayName": "137309343814",
                "ID": "bf27a534c828c92588adaf938a7396fb7ef9e027350cc4187a47d858c1f460d7",
                "Type": "CanonicalUser"
            },
            "Permission": "FULL_CONTROL"
        }
    ]
}
```

Change access control:

```sh
$ aws s3api put-bucket-acl --bucket resana-secure-demo-blocks --endpoint https://oos.cloudgouv-eu-west-1.outscale.com/ --grant-write="emailaddress=name@domain.com"
```

This will remove you own access unless you pass `--grant-full-control='id=<your ID retrieved from get-bucket-acl>'`.
No matter what you are still owner of the bucket and are still allowed to change the access control.

[See documentation](https://docs.outscale.com/fr/userguide/Configurer-l-ACL-d-un-bucket.html)

## 5 Cleanup when you're done

!!! Remember to remove the file `~/.aws/credentials` when you're done !!!
