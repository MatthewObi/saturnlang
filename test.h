#define CLASS(T, body) typedef struct body T;
struct Vector3 {
    int x;
    const int y;
    int z;
};

CLASS(Node, {
    int left;
    int right;
})

typedef struct Vector3 Vector3;

int test(float *param) {
    Vector3 v = {5, 17, 0};
    *param = 4.5f;
    return v.x;
}

//void myfunc(char* x, char** y, const char* z, Vector3 *v4) {}