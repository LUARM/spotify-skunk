rm -fr dependencies 
pip install \
    --platform manylinux2014_x86_64 \
    --target=dependencies \
    --implementation cp \
    --python-version 3.9 \
    --only-binary=:all: --upgrade \
    -r requirements.txt